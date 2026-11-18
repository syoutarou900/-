# -*- coding: utf-8 -*-
"""Screen recording for StepOnce.

Design rules:
- Typed keyboard content is NEVER recorded. Only the fact that a control
  was clicked, plus the control's name/type, reaches a step.
- The OS-specific parts are isolated in this module. The step-building
  pipeline (screenshot -> element info -> Step) is shared, and tests can
  inject a FakeRecorder / fake element provider, so the whole draft
  generation path is testable on any OS.
- Windows: automatic recording. A low-level mouse hook (ctypes) reports
  clicks; UI Automation (ctypes COM) identifies the clicked element.
  Clicks inside this app's own processes are ignored (so the recording
  panel's own buttons do not become steps).
- macOS: manual capture only. Automatic click tracking would need
  Accessibility permission and a dedicated implementation that cannot be
  verified without a Mac, so the app adds steps when the user presses
  the capture button / hotkey instead.
"""

import os
import queue
import sys
import threading
import time
from dataclasses import dataclass

from PIL import ImageGrab

import core
from core import Step, Rect

# UIA control type ids -> draft kinds
_CT_BUTTON = 50000
_CT_CHECKBOX = 50002
_CT_COMBOBOX = 50003
_CT_EDIT = 50004
_CT_MENUITEM = 50011
_CT_RADIOBUTTON = 50013
_CT_TABITEM = 50019
_CT_TREEITEM = 50024
_CT_DOCUMENT = 50030
_CT_SPLITBUTTON = 50031
_CT_APPBAR = 50032


def kind_for_control_type(control_type):
    if control_type in (_CT_BUTTON, _CT_SPLITBUTTON, _CT_APPBAR):
        return core.KIND_BUTTON
    if control_type in (_CT_EDIT, _CT_DOCUMENT):
        return core.KIND_INPUT
    if control_type in (_CT_COMBOBOX, _CT_MENUITEM, _CT_TABITEM,
                        _CT_TREEITEM):
        return core.KIND_OPEN
    return core.KIND_NAMED


@dataclass
class ElementInfo:
    name: str = ""
    control_type: int = 0
    is_password: bool = False
    rect: tuple = None          # (left, top, width, height) in screen px
    window_title: str = ""
    process_id: int = 0


def build_step(image, element, click_xy, origin=(0, 0)):
    """Build a Step from a captured screenshot and (optional) element
    info. `click_xy` and `origin` are absolute screen pixels; the stored
    click/mosaic coordinates are relative fractions."""
    step = Step()
    w, h = image.size
    if click_xy is not None:
        rel_x = (click_xy[0] - origin[0]) / w if w else 0.0
        rel_y = (click_xy[1] - origin[1]) / h if h else 0.0
        step.click = (min(1.0, max(0.0, rel_x)), min(1.0, max(0.0, rel_y)))
    if element is None:
        step.kind = core.KIND_MANUAL if click_xy is None \
            else core.KIND_GENERIC
        return step
    step.target_name = element.name or ""
    step.window_title = element.window_title or ""
    if step.target_name:
        step.kind = kind_for_control_type(element.control_type)
    else:
        step.kind = core.KIND_GENERIC
    if element.rect and core.looks_like_password(element.name,
                                                 element.is_password):
        left, top, ew, eh = element.rect
        step.mosaic_candidates.append(Rect.from_pixels(
            left - origin[0], top - origin[1],
            left - origin[0] + ew, top - origin[1] + eh, w, h))
    return step


def grab_screen():
    """Return (PIL image of the whole virtual screen, (origin_x,
    origin_y))."""
    origin = (0, 0)
    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            origin = (user32.GetSystemMetrics(76),   # SM_XVIRTUALSCREEN
                      user32.GetSystemMetrics(77))   # SM_YVIRTUALSCREEN
        except Exception:
            origin = (0, 0)
    try:
        img = ImageGrab.grab(all_screens=True)
    except TypeError:
        img = ImageGrab.grab()
    return img.convert("RGB"), origin


# ----------------------------------------------------------------------
# Recorders
# ----------------------------------------------------------------------

class BaseRecorder:
    mode = "manual"  # or "auto"

    def __init__(self, on_step):
        self.on_step = on_step    # callable(step, pil_image)
        self.running = False
        self.paused = False

    def start(self):
        self.running = True
        self.paused = False

    def stop(self):
        self.running = False
        self.paused = False

    def set_paused(self, paused):
        self.paused = bool(paused)


class FakeRecorder(BaseRecorder):
    """Test double: feeds synthetic captures through the same pipeline
    as the real recorders."""

    mode = "auto"

    def feed(self, image, element=None, click_xy=None, origin=(0, 0)):
        if not self.running or self.paused:
            return None
        step = build_step(image, element, click_xy, origin)
        self.on_step(step, image)
        return step


class ManualCapturer:
    """One-shot screen capture used by the capture button / hotkey on
    every platform (the only capture method on macOS)."""

    def __init__(self, on_step):
        self.on_step = on_step

    def capture_now(self, window_title=""):
        img, origin = grab_screen()
        element = ElementInfo(name="", window_title=window_title)
        step = build_step(img, element, None, origin)
        step.kind = core.KIND_MANUAL
        self.on_step(step, img)
        return step


# ----------------------------------------------------------------------
# Windows UI Automation via ctypes COM
# ----------------------------------------------------------------------

_UIA_NAME = 30005
_UIA_CONTROL_TYPE = 30003
_UIA_IS_PASSWORD = 30019
_UIA_BOUNDING_RECT = 30001
_UIA_PROCESS_ID = 30002


def _guid(text):
    import ctypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]
    import uuid
    u = uuid.UUID(text)
    g = GUID()
    g.Data1 = u.time_low
    g.Data2 = u.time_mid
    g.Data3 = u.time_hi_version
    for i, b in enumerate(u.bytes[8:]):
        g.Data4[i] = b
    return g


def _make_variant():
    import ctypes

    class VARIANT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("lVal", ctypes.c_long),
                        ("dblVal", ctypes.c_double),
                        ("boolVal", ctypes.c_short),
                        ("bstrVal", ctypes.c_void_p),
                        ("parray", ctypes.c_void_p)]
        _anonymous_ = ("u",)
        _fields_ = [("vt", ctypes.c_ushort),
                    ("wReserved1", ctypes.c_ushort),
                    ("wReserved2", ctypes.c_ushort),
                    ("wReserved3", ctypes.c_ushort),
                    ("u", _U)]
    return VARIANT


def _com_call(ptr, index, restype, *argtypes_and_args):
    """Call an interface method by vtable index."""
    import ctypes
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0]
    func_ptr = ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))[index]
    argtypes = [ctypes.c_void_p] + [a[0] for a in argtypes_and_args]
    args = [ptr] + [a[1] for a in argtypes_and_args]
    func = ctypes.WINFUNCTYPE(restype, *argtypes)(func_ptr)
    return func(*args)


class UiaElementProvider:
    """ElementFromPoint using IUIAutomation through ctypes. COM is
    initialized per calling thread."""

    def __init__(self):
        self._automation = None

    def _ensure(self):
        import ctypes
        if self._automation is not None:
            return True
        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
        clsid = _guid("FF48DBA4-60EF-4201-AA87-54103EEF594E")
        iid = _guid("30CBE57D-D9D0-452A-AB13-7AC5AC4825EE")
        ptr = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 0x17,
                                    ctypes.byref(iid), ctypes.byref(ptr))
        if hr != 0 or not ptr:
            return False
        self._automation = ptr
        return True

    def element_from_point(self, x, y):
        import ctypes
        if not self._ensure():
            return None
        # IUIAutomation::ElementFromPoint is vtable index 5.
        pt = ctypes.c_long(x), ctypes.c_long(y)
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        elem = ctypes.c_void_p()
        hr = _com_call(self._automation, 5, ctypes.c_long,
                       (POINT, POINT(x, y)), (ctypes.c_void_p,
                                              ctypes.byref(elem)))
        if hr != 0 or not elem:
            return None
        try:
            return self._read_element(elem)
        finally:
            _com_call(elem, 2, ctypes.c_ulong)  # Release

    def _prop(self, elem, prop_id):
        import ctypes
        VARIANT = _make_variant()
        var = VARIANT()
        # IUIAutomationElement::GetCurrentPropertyValue is index 10.
        hr = _com_call(elem, 10, ctypes.c_long,
                       (ctypes.c_int, prop_id),
                       (ctypes.POINTER(VARIANT), ctypes.byref(var)))
        if hr != 0:
            return None
        return var

    def _read_element(self, elem):
        import ctypes
        info = ElementInfo()
        var = self._prop(elem, _UIA_NAME)
        if var is not None and var.vt == 8 and var.bstrVal:  # VT_BSTR
            info.name = ctypes.wstring_at(var.bstrVal)
        var = self._prop(elem, _UIA_CONTROL_TYPE)
        if var is not None and var.vt == 3:  # VT_I4
            info.control_type = int(var.lVal)
        var = self._prop(elem, _UIA_PROCESS_ID)
        if var is not None and var.vt == 3:
            info.process_id = int(var.lVal)
        var = self._prop(elem, _UIA_IS_PASSWORD)
        if var is not None and var.vt == 11:  # VT_BOOL
            info.is_password = bool(var.boolVal)
        var = self._prop(elem, _UIA_BOUNDING_RECT)
        if var is not None and var.vt == 0x2005 and var.parray:  # VT_ARRAY|R8
            info.rect = self._read_rect_array(var.parray)
        info.window_title = self._top_window_title(elem)
        return info

    @staticmethod
    def _read_rect_array(parray):
        import ctypes

        class SAFEARRAY(ctypes.Structure):
            _fields_ = [("cDims", ctypes.c_ushort),
                        ("fFeatures", ctypes.c_ushort),
                        ("cbElements", ctypes.c_ulong),
                        ("cLocks", ctypes.c_ulong),
                        ("pvData", ctypes.c_void_p),
                        ("rgsabound", ctypes.c_ulong * 4)]
        sa = ctypes.cast(parray, ctypes.POINTER(SAFEARRAY)).contents
        if not sa.pvData:
            return None
        vals = (ctypes.c_double * 4).from_address(sa.pvData)
        return (int(vals[0]), int(vals[1]), int(vals[2]), int(vals[3]))

    def _top_window_title(self, elem):
        """Best effort: foreground window title at capture time."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return ""
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            return buf.value
        except Exception:
            return ""


class WindowsAutoRecorder(BaseRecorder):
    """Automatic recording on Windows: low-level mouse hook thread feeds
    a queue; a capture thread takes the screenshot and queries UIA."""

    mode = "auto"

    def __init__(self, on_step, element_provider=None, grabber=None):
        super().__init__(on_step)
        self._queue = queue.Queue()
        self._hook_thread = None
        self._capture_thread = None
        self._stop_event = threading.Event()
        self._provider = element_provider or (
            UiaElementProvider() if sys.platform == "win32" else None)
        self._grabber = grabber or grab_screen
        self._own_pid = os.getpid()
        self._last_click = (None, 0.0)

    # -- lifecycle ------------------------------------------------------
    def start(self):
        if sys.platform != "win32":
            raise RuntimeError("WindowsAutoRecorder requires Windows")
        super().start()
        self._stop_event.clear()
        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        self._hook_thread = threading.Thread(
            target=self._hook_loop, daemon=True)
        self._hook_thread.start()

    def stop(self):
        super().stop()
        self._stop_event.set()
        if self._hook_thread:
            try:
                import ctypes
                tid = self._hook_thread.native_id
                if tid:
                    ctypes.windll.user32.PostThreadMessageW(
                        tid, 0x0012, 0, 0)  # WM_QUIT
            except Exception:
                pass

    # -- hook thread ----------------------------------------------------
    def _hook_loop(self):
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        WH_MOUSE_LL = 14
        WM_LBUTTONDOWN = 0x0201

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("pt", POINT), ("mouseData", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_void_p)]

        HOOKPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        queue_ref = self._queue

        def proc(ncode, wparam, lparam):
            if ncode >= 0 and wparam == WM_LBUTTONDOWN:
                ms = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT))
                queue_ref.put((ms.contents.pt.x, ms.contents.pt.y))
            return user32.CallNextHookEx(None, ncode, wparam, lparam)

        callback = HOOKPROC(proc)
        hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, callback, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            return
        msg = wintypes.MSG()
        try:
            while not self._stop_event.is_set():
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnhookWindowsHookEx(hook)

    # -- capture thread ---------------------------------------------------
    def _capture_loop(self):
        while not self._stop_event.is_set():
            try:
                x, y = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if self.paused or not self.running:
                continue
            # collapse double events for the same point in quick succession
            now = time.time()
            if self._last_click[0] == (x, y) and now - self._last_click[1] < 0.35:
                continue
            self._last_click = ((x, y), now)
            self.process_click(x, y)

    def process_click(self, x, y):
        """Screenshot + element lookup + step build for one click.
        Factored out so tests can drive it with injected fakes."""
        element = None
        if self._provider is not None:
            try:
                element = self._provider.element_from_point(x, y)
            except Exception:
                element = None
        if element is not None and element.process_id == self._own_pid:
            return None     # our own UI (recording panel etc.)
        image, origin = self._grabber()
        step = build_step(image, element, (x, y), origin)
        self.on_step(step, image)
        return step


def create_recorder(on_step):
    """Platform factory: automatic recording on Windows, manual capture
    elsewhere (macOS)."""
    if sys.platform == "win32":
        return WindowsAutoRecorder(on_step)
    recorder = BaseRecorder(on_step)
    recorder.mode = "manual"
    return recorder
