# -*- coding: utf-8 -*-
"""UI strings and proposal templates in 13 languages for GlobalHours.

LANGS lists the supported UI languages in display order. STRINGS maps
language -> key -> text; missing keys fall back to English.
PROPOSALS maps language -> a meeting-proposal template with the
placeholders {name}, {own_time}, {own_city}, {partner_time},
{partner_city}.
"""

LANGS = [
    ("ja", "日本語"), ("en", "English"), ("es", "Español"),
    ("zh", "简体中文"), ("fr", "Français"), ("de", "Deutsch"),
    ("pt", "Português"), ("ru", "Русский"), ("it", "Italiano"),
    ("tr", "Türkçe"), ("ar", "العربية"), ("id", "Bahasa Indonesia"),
    ("ko", "한국어"),
]
LANG_CODES = [c for c, _n in LANGS]
RTL_LANGS = {"ar"}

STRINGS = {
    "ja": {
        "own_group": "自分の場所", "own_zone": "タイムゾーン",
        "own_country": "自分の国", "work_hours": "営業時間",
        "start": "開始", "end": "終了",
        "partners_group": "取引先", "add": "追加", "edit": "編集",
        "delete": "削除",
        "check_group": "日時をチェック", "date_time": "自分の日時",
        "now_button": "現在時刻", "check_button": "チェック",
        "col_partner": "取引先", "col_local_time": "現地時間",
        "col_offset": "時差", "col_status": "状態",
        "status_ok": "営業時間内", "status_outside": "営業時間外",
        "status_weekend": "週末", "status_holiday": "祝日",
        "dst_warning": "{date} に夏時間の切り替え",
        "slots_group": "候補の時間帯", "from_date": "開始日",
        "days": "日数", "duration": "長さ（分）", "find_slots": "候補を探す",
        "no_slots": "双方の営業時間に収まる候補はありませんでした。",
        "slot_count": "{count} 件の候補が見つかりました",
        "col_own_time": "自分の時間", "col_partner_time": "相手の時間",
        "proposal_group": "提案文", "partner_label": "取引先",
        "language_label": "言語", "copy_button": "コピー",
        "copied": "コピーしました",
        "dlg_add": "取引先を追加", "dlg_edit": "取引先を編集",
        "f_name": "名前", "f_country": "国", "f_city": "都市",
        "f_zone": "タイムゾーン", "f_lang": "提案文の言語",
        "auto": "自動", "delete_confirm": "この取引先を削除しますか？",
        "no_partners": "取引先がまだ登録されていません。追加するとチェックできます。",
        "select_partner": "取引先を選んでください",
        "save": "保存", "cancel": "キャンセル",
        "use_slot": "この候補を提案文に使う",
        "own_label": "自分",
    },
    "en": {
        "own_group": "Your location", "own_zone": "Your timezone",
        "own_country": "Your country", "work_hours": "Business hours",
        "start": "Start", "end": "End",
        "partners_group": "Partners", "add": "Add", "edit": "Edit",
        "delete": "Delete",
        "check_group": "Check a date & time", "date_time": "Your date & time",
        "now_button": "Now", "check_button": "Check",
        "col_partner": "Partner", "col_local_time": "Local time",
        "col_offset": "Offset", "col_status": "Status",
        "status_ok": "In business hours", "status_outside": "Outside hours",
        "status_weekend": "Weekend", "status_holiday": "Holiday",
        "dst_warning": "Daylight saving changes on {date}",
        "slots_group": "Candidate time slots", "from_date": "From",
        "days": "Days", "duration": "Duration (min)", "find_slots": "Find slots",
        "no_slots": "No slot fits both sides' business hours.",
        "slot_count": "{count} slot(s) found",
        "col_own_time": "Your time", "col_partner_time": "Partner time",
        "proposal_group": "Proposal message", "partner_label": "Partner",
        "language_label": "Language", "copy_button": "Copy",
        "copied": "Copied",
        "dlg_add": "Add partner", "dlg_edit": "Edit partner",
        "f_name": "Name", "f_country": "Country", "f_city": "City",
        "f_zone": "Timezone", "f_lang": "Proposal language",
        "auto": "Auto", "delete_confirm": "Delete this partner?",
        "no_partners": "No partners registered yet. Add one to start checking.",
        "select_partner": "Select a partner",
        "save": "Save", "cancel": "Cancel",
        "use_slot": "Use this slot in the proposal",
        "own_label": "You",
    },
    "es": {
        "own_group": "Su ubicación", "own_zone": "Su zona horaria",
        "own_country": "Su país", "work_hours": "Horario laboral",
        "start": "Inicio", "end": "Fin",
        "partners_group": "Contactos", "add": "Añadir", "edit": "Editar",
        "delete": "Eliminar",
        "check_group": "Comprobar fecha y hora", "date_time": "Su fecha y hora",
        "now_button": "Ahora", "check_button": "Comprobar",
        "col_partner": "Contacto", "col_local_time": "Hora local",
        "col_offset": "Diferencia", "col_status": "Estado",
        "status_ok": "En horario laboral", "status_outside": "Fuera de horario",
        "status_weekend": "Fin de semana", "status_holiday": "Festivo",
        "dst_warning": "Cambio de horario de verano el {date}",
        "slots_group": "Horarios candidatos", "from_date": "Desde",
        "days": "Días", "duration": "Duración (min)", "find_slots": "Buscar horarios",
        "no_slots": "Ningún horario encaja en el horario laboral de ambos.",
        "slot_count": "{count} horario(s) encontrado(s)",
        "col_own_time": "Su hora", "col_partner_time": "Hora del contacto",
        "proposal_group": "Mensaje de propuesta", "partner_label": "Contacto",
        "language_label": "Idioma", "copy_button": "Copiar",
        "copied": "Copiado",
        "dlg_add": "Añadir contacto", "dlg_edit": "Editar contacto",
        "f_name": "Nombre", "f_country": "País", "f_city": "Ciudad",
        "f_zone": "Zona horaria", "f_lang": "Idioma de la propuesta",
        "auto": "Automático", "delete_confirm": "¿Eliminar este contacto?",
        "no_partners": "Aún no hay contactos. Añada uno para empezar.",
        "select_partner": "Seleccione un contacto",
        "save": "Guardar", "cancel": "Cancelar",
        "use_slot": "Usar este horario en la propuesta",
        "own_label": "Usted",
    },
    "zh": {
        "own_group": "您的位置", "own_zone": "您的时区",
        "own_country": "您的国家", "work_hours": "营业时间",
        "start": "开始", "end": "结束",
        "partners_group": "联系人", "add": "添加", "edit": "编辑",
        "delete": "删除",
        "check_group": "检查日期和时间", "date_time": "您的日期和时间",
        "now_button": "现在", "check_button": "检查",
        "col_partner": "联系人", "col_local_time": "当地时间",
        "col_offset": "时差", "col_status": "状态",
        "status_ok": "营业时间内", "status_outside": "营业时间外",
        "status_weekend": "周末", "status_holiday": "节假日",
        "dst_warning": "{date} 夏令时切换",
        "slots_group": "候选时间段", "from_date": "开始日期",
        "days": "天数", "duration": "时长（分钟）", "find_slots": "查找时间段",
        "no_slots": "没有同时符合双方营业时间的时间段。",
        "slot_count": "找到 {count} 个时间段",
        "col_own_time": "您的时间", "col_partner_time": "对方的时间",
        "proposal_group": "提议消息", "partner_label": "联系人",
        "language_label": "语言", "copy_button": "复制",
        "copied": "已复制",
        "dlg_add": "添加联系人", "dlg_edit": "编辑联系人",
        "f_name": "名称", "f_country": "国家", "f_city": "城市",
        "f_zone": "时区", "f_lang": "提议语言",
        "auto": "自动", "delete_confirm": "删除此联系人？",
        "no_partners": "尚未注册联系人。添加后即可开始检查。",
        "select_partner": "请选择联系人",
        "save": "保存", "cancel": "取消",
        "use_slot": "在提议中使用此时间段",
        "own_label": "您",
    },
    "fr": {
        "own_group": "Votre emplacement", "own_zone": "Votre fuseau horaire",
        "own_country": "Votre pays", "work_hours": "Heures d'ouverture",
        "start": "Début", "end": "Fin",
        "partners_group": "Partenaires", "add": "Ajouter", "edit": "Modifier",
        "delete": "Supprimer",
        "check_group": "Vérifier une date et une heure",
        "date_time": "Votre date et heure",
        "now_button": "Maintenant", "check_button": "Vérifier",
        "col_partner": "Partenaire", "col_local_time": "Heure locale",
        "col_offset": "Décalage", "col_status": "Statut",
        "status_ok": "Heures d'ouverture", "status_outside": "Hors horaires",
        "status_weekend": "Week-end", "status_holiday": "Jour férié",
        "dst_warning": "Changement d'heure d'été le {date}",
        "slots_group": "Créneaux candidats", "from_date": "À partir du",
        "days": "Jours", "duration": "Durée (min)", "find_slots": "Rechercher",
        "no_slots": "Aucun créneau ne convient aux deux horaires.",
        "slot_count": "{count} créneau(x) trouvé(s)",
        "col_own_time": "Votre heure", "col_partner_time": "Heure du partenaire",
        "proposal_group": "Message de proposition", "partner_label": "Partenaire",
        "language_label": "Langue", "copy_button": "Copier",
        "copied": "Copié",
        "dlg_add": "Ajouter un partenaire", "dlg_edit": "Modifier le partenaire",
        "f_name": "Nom", "f_country": "Pays", "f_city": "Ville",
        "f_zone": "Fuseau horaire", "f_lang": "Langue de la proposition",
        "auto": "Automatique", "delete_confirm": "Supprimer ce partenaire ?",
        "no_partners": "Aucun partenaire enregistré. Ajoutez-en un pour commencer.",
        "select_partner": "Sélectionnez un partenaire",
        "save": "Enregistrer", "cancel": "Annuler",
        "use_slot": "Utiliser ce créneau dans la proposition",
        "own_label": "Vous",
    },
    "de": {
        "own_group": "Ihr Standort", "own_zone": "Ihre Zeitzone",
        "own_country": "Ihr Land", "work_hours": "Geschäftszeiten",
        "start": "Beginn", "end": "Ende",
        "partners_group": "Partner", "add": "Hinzufügen", "edit": "Bearbeiten",
        "delete": "Löschen",
        "check_group": "Datum und Uhrzeit prüfen", "date_time": "Ihr Datum und Ihre Uhrzeit",
        "now_button": "Jetzt", "check_button": "Prüfen",
        "col_partner": "Partner", "col_local_time": "Ortszeit",
        "col_offset": "Zeitunterschied", "col_status": "Status",
        "status_ok": "In den Geschäftszeiten", "status_outside": "Außerhalb der Geschäftszeiten",
        "status_weekend": "Wochenende", "status_holiday": "Feiertag",
        "dst_warning": "Zeitumstellung am {date}",
        "slots_group": "Mögliche Zeitfenster", "from_date": "Ab",
        "days": "Tage", "duration": "Dauer (Min.)", "find_slots": "Zeitfenster suchen",
        "no_slots": "Kein Zeitfenster passt zu beiden Geschäftszeiten.",
        "slot_count": "{count} Zeitfenster gefunden",
        "col_own_time": "Ihre Zeit", "col_partner_time": "Zeit des Partners",
        "proposal_group": "Vorschlagsnachricht", "partner_label": "Partner",
        "language_label": "Sprache", "copy_button": "Kopieren",
        "copied": "Kopiert",
        "dlg_add": "Partner hinzufügen", "dlg_edit": "Partner bearbeiten",
        "f_name": "Name", "f_country": "Land", "f_city": "Stadt",
        "f_zone": "Zeitzone", "f_lang": "Sprache des Vorschlags",
        "auto": "Automatisch", "delete_confirm": "Diesen Partner löschen?",
        "no_partners": "Noch keine Partner registriert. Fügen Sie einen hinzu.",
        "select_partner": "Wählen Sie einen Partner",
        "save": "Speichern", "cancel": "Abbrechen",
        "use_slot": "Dieses Zeitfenster im Vorschlag verwenden",
        "own_label": "Sie",
    },
    "pt": {
        "own_group": "A sua localização", "own_zone": "O seu fuso horário",
        "own_country": "O seu país", "work_hours": "Horário comercial",
        "start": "Início", "end": "Fim",
        "partners_group": "Parceiros", "add": "Adicionar", "edit": "Editar",
        "delete": "Eliminar",
        "check_group": "Verificar data e hora", "date_time": "A sua data e hora",
        "now_button": "Agora", "check_button": "Verificar",
        "col_partner": "Parceiro", "col_local_time": "Hora local",
        "col_offset": "Diferença", "col_status": "Estado",
        "status_ok": "Em horário comercial", "status_outside": "Fora de horário",
        "status_weekend": "Fim de semana", "status_holiday": "Feriado",
        "dst_warning": "Mudança de horário de verão em {date}",
        "slots_group": "Horários candidatos", "from_date": "De",
        "days": "Dias", "duration": "Duração (min)", "find_slots": "Procurar horários",
        "no_slots": "Nenhum horário cabe no horário comercial de ambos.",
        "slot_count": "{count} horário(s) encontrado(s)",
        "col_own_time": "A sua hora", "col_partner_time": "Hora do parceiro",
        "proposal_group": "Mensagem de proposta", "partner_label": "Parceiro",
        "language_label": "Idioma", "copy_button": "Copiar",
        "copied": "Copiado",
        "dlg_add": "Adicionar parceiro", "dlg_edit": "Editar parceiro",
        "f_name": "Nome", "f_country": "País", "f_city": "Cidade",
        "f_zone": "Fuso horário", "f_lang": "Idioma da proposta",
        "auto": "Automático", "delete_confirm": "Eliminar este parceiro?",
        "no_partners": "Ainda não há parceiros. Adicione um para começar.",
        "select_partner": "Selecione um parceiro",
        "save": "Guardar", "cancel": "Cancelar",
        "use_slot": "Usar este horário na proposta",
        "own_label": "Você",
    },
    "ru": {
        "own_group": "Ваше местоположение", "own_zone": "Ваш часовой пояс",
        "own_country": "Ваша страна", "work_hours": "Рабочее время",
        "start": "Начало", "end": "Конец",
        "partners_group": "Партнёры", "add": "Добавить", "edit": "Изменить",
        "delete": "Удалить",
        "check_group": "Проверить дату и время", "date_time": "Ваши дата и время",
        "now_button": "Сейчас", "check_button": "Проверить",
        "col_partner": "Партнёр", "col_local_time": "Местное время",
        "col_offset": "Разница", "col_status": "Статус",
        "status_ok": "Рабочее время", "status_outside": "Нерабочее время",
        "status_weekend": "Выходной", "status_holiday": "Праздник",
        "dst_warning": "Переход на летнее/зимнее время: {date}",
        "slots_group": "Подходящее время", "from_date": "С",
        "days": "Дней", "duration": "Длительность (мин)", "find_slots": "Найти время",
        "no_slots": "Нет времени, подходящего обеим сторонам.",
        "slot_count": "Найдено вариантов: {count}",
        "col_own_time": "Ваше время", "col_partner_time": "Время партнёра",
        "proposal_group": "Текст предложения", "partner_label": "Партнёр",
        "language_label": "Язык", "copy_button": "Копировать",
        "copied": "Скопировано",
        "dlg_add": "Добавить партнёра", "dlg_edit": "Изменить партнёра",
        "f_name": "Название", "f_country": "Страна", "f_city": "Город",
        "f_zone": "Часовой пояс", "f_lang": "Язык предложения",
        "auto": "Автоматически", "delete_confirm": "Удалить этого партнёра?",
        "no_partners": "Партнёры ещё не добавлены. Добавьте первого.",
        "select_partner": "Выберите партнёра",
        "save": "Сохранить", "cancel": "Отмена",
        "use_slot": "Использовать это время в предложении",
        "own_label": "Вы",
    },
    "it": {
        "own_group": "La tua posizione", "own_zone": "Il tuo fuso orario",
        "own_country": "Il tuo paese", "work_hours": "Orario di lavoro",
        "start": "Inizio", "end": "Fine",
        "partners_group": "Partner", "add": "Aggiungi", "edit": "Modifica",
        "delete": "Elimina",
        "check_group": "Controlla data e ora", "date_time": "La tua data e ora",
        "now_button": "Ora", "check_button": "Controlla",
        "col_partner": "Partner", "col_local_time": "Ora locale",
        "col_offset": "Differenza", "col_status": "Stato",
        "status_ok": "In orario di lavoro", "status_outside": "Fuori orario",
        "status_weekend": "Fine settimana", "status_holiday": "Festivo",
        "dst_warning": "Cambio ora legale il {date}",
        "slots_group": "Orari candidati", "from_date": "Dal",
        "days": "Giorni", "duration": "Durata (min)", "find_slots": "Trova orari",
        "no_slots": "Nessun orario rientra in entrambi gli orari di lavoro.",
        "slot_count": "{count} orario/i trovato/i",
        "col_own_time": "La tua ora", "col_partner_time": "Ora del partner",
        "proposal_group": "Messaggio di proposta", "partner_label": "Partner",
        "language_label": "Lingua", "copy_button": "Copia",
        "copied": "Copiato",
        "dlg_add": "Aggiungi partner", "dlg_edit": "Modifica partner",
        "f_name": "Nome", "f_country": "Paese", "f_city": "Città",
        "f_zone": "Fuso orario", "f_lang": "Lingua della proposta",
        "auto": "Automatico", "delete_confirm": "Eliminare questo partner?",
        "no_partners": "Nessun partner registrato. Aggiungine uno per iniziare.",
        "select_partner": "Seleziona un partner",
        "save": "Salva", "cancel": "Annulla",
        "use_slot": "Usa questo orario nella proposta",
        "own_label": "Tu",
    },
    "tr": {
        "own_group": "Konumunuz", "own_zone": "Saat diliminiz",
        "own_country": "Ülkeniz", "work_hours": "Çalışma saatleri",
        "start": "Başlangıç", "end": "Bitiş",
        "partners_group": "İş ortakları", "add": "Ekle", "edit": "Düzenle",
        "delete": "Sil",
        "check_group": "Tarih ve saat kontrolü", "date_time": "Tarih ve saatiniz",
        "now_button": "Şimdi", "check_button": "Kontrol et",
        "col_partner": "İş ortağı", "col_local_time": "Yerel saat",
        "col_offset": "Fark", "col_status": "Durum",
        "status_ok": "Çalışma saatleri içinde", "status_outside": "Çalışma saatleri dışında",
        "status_weekend": "Hafta sonu", "status_holiday": "Resmi tatil",
        "dst_warning": "{date} tarihinde yaz saati değişimi",
        "slots_group": "Uygun zaman adayları", "from_date": "Başlangıç",
        "days": "Gün", "duration": "Süre (dk)", "find_slots": "Zaman bul",
        "no_slots": "Her iki tarafın çalışma saatlerine uyan zaman yok.",
        "slot_count": "{count} uygun zaman bulundu",
        "col_own_time": "Sizin saatiniz", "col_partner_time": "Ortağın saati",
        "proposal_group": "Teklif mesajı", "partner_label": "İş ortağı",
        "language_label": "Dil", "copy_button": "Kopyala",
        "copied": "Kopyalandı",
        "dlg_add": "İş ortağı ekle", "dlg_edit": "İş ortağını düzenle",
        "f_name": "Ad", "f_country": "Ülke", "f_city": "Şehir",
        "f_zone": "Saat dilimi", "f_lang": "Teklif dili",
        "auto": "Otomatik", "delete_confirm": "Bu iş ortağı silinsin mi?",
        "no_partners": "Henüz iş ortağı yok. Başlamak için ekleyin.",
        "select_partner": "Bir iş ortağı seçin",
        "save": "Kaydet", "cancel": "İptal",
        "use_slot": "Bu zamanı teklifte kullan",
        "own_label": "Siz",
    },
    "ar": {
        "own_group": "موقعك", "own_zone": "منطقتك الزمنية",
        "own_country": "بلدك", "work_hours": "ساعات العمل",
        "start": "البدء", "end": "الانتهاء",
        "partners_group": "الشركاء", "add": "إضافة", "edit": "تعديل",
        "delete": "حذف",
        "check_group": "التحقق من التاريخ والوقت", "date_time": "التاريخ والوقت لديك",
        "now_button": "الآن", "check_button": "تحقق",
        "col_partner": "الشريك", "col_local_time": "الوقت المحلي",
        "col_offset": "الفرق", "col_status": "الحالة",
        "status_ok": "ضمن ساعات العمل", "status_outside": "خارج ساعات العمل",
        "status_weekend": "عطلة نهاية الأسبوع", "status_holiday": "عطلة رسمية",
        "dst_warning": "تغيير التوقيت الصيفي في {date}",
        "slots_group": "الأوقات المقترحة", "from_date": "من",
        "days": "أيام", "duration": "المدة (دقيقة)", "find_slots": "بحث عن أوقات",
        "no_slots": "لا يوجد وقت يناسب ساعات عمل الطرفين.",
        "slot_count": "تم العثور على {count} وقت",
        "col_own_time": "وقتك", "col_partner_time": "وقت الشريك",
        "proposal_group": "رسالة الاقتراح", "partner_label": "الشريك",
        "language_label": "اللغة", "copy_button": "نسخ",
        "copied": "تم النسخ",
        "dlg_add": "إضافة شريك", "dlg_edit": "تعديل الشريك",
        "f_name": "الاسم", "f_country": "البلد", "f_city": "المدينة",
        "f_zone": "المنطقة الزمنية", "f_lang": "لغة الاقتراح",
        "auto": "تلقائي", "delete_confirm": "حذف هذا الشريك؟",
        "no_partners": "لا يوجد شركاء بعد. أضف واحدًا للبدء.",
        "select_partner": "اختر شريكًا",
        "save": "حفظ", "cancel": "إلغاء",
        "use_slot": "استخدام هذا الوقت في الاقتراح",
        "own_label": "أنت",
    },
    "id": {
        "own_group": "Lokasi Anda", "own_zone": "Zona waktu Anda",
        "own_country": "Negara Anda", "work_hours": "Jam kerja",
        "start": "Mulai", "end": "Selesai",
        "partners_group": "Mitra", "add": "Tambah", "edit": "Ubah",
        "delete": "Hapus",
        "check_group": "Periksa tanggal & waktu", "date_time": "Tanggal & waktu Anda",
        "now_button": "Sekarang", "check_button": "Periksa",
        "col_partner": "Mitra", "col_local_time": "Waktu setempat",
        "col_offset": "Selisih", "col_status": "Status",
        "status_ok": "Dalam jam kerja", "status_outside": "Di luar jam kerja",
        "status_weekend": "Akhir pekan", "status_holiday": "Hari libur",
        "dst_warning": "Perubahan waktu musim panas pada {date}",
        "slots_group": "Pilihan waktu", "from_date": "Dari",
        "days": "Hari", "duration": "Durasi (menit)", "find_slots": "Cari waktu",
        "no_slots": "Tidak ada waktu yang cocok untuk kedua jam kerja.",
        "slot_count": "{count} pilihan waktu ditemukan",
        "col_own_time": "Waktu Anda", "col_partner_time": "Waktu mitra",
        "proposal_group": "Pesan usulan", "partner_label": "Mitra",
        "language_label": "Bahasa", "copy_button": "Salin",
        "copied": "Tersalin",
        "dlg_add": "Tambah mitra", "dlg_edit": "Ubah mitra",
        "f_name": "Nama", "f_country": "Negara", "f_city": "Kota",
        "f_zone": "Zona waktu", "f_lang": "Bahasa usulan",
        "auto": "Otomatis", "delete_confirm": "Hapus mitra ini?",
        "no_partners": "Belum ada mitra. Tambahkan satu untuk memulai.",
        "select_partner": "Pilih mitra",
        "save": "Simpan", "cancel": "Batal",
        "use_slot": "Gunakan waktu ini dalam usulan",
        "own_label": "Anda",
    },
    "ko": {
        "own_group": "내 위치", "own_zone": "내 시간대",
        "own_country": "내 국가", "work_hours": "영업 시간",
        "start": "시작", "end": "종료",
        "partners_group": "거래처", "add": "추가", "edit": "편집",
        "delete": "삭제",
        "check_group": "날짜와 시간 확인", "date_time": "내 날짜와 시간",
        "now_button": "현재 시간", "check_button": "확인",
        "col_partner": "거래처", "col_local_time": "현지 시간",
        "col_offset": "시차", "col_status": "상태",
        "status_ok": "영업 시간 내", "status_outside": "영업 시간 외",
        "status_weekend": "주말", "status_holiday": "공휴일",
        "dst_warning": "{date} 서머타임 전환",
        "slots_group": "후보 시간대", "from_date": "시작일",
        "days": "일수", "duration": "길이(분)", "find_slots": "후보 찾기",
        "no_slots": "양쪽 영업 시간에 맞는 후보가 없습니다.",
        "slot_count": "후보 {count}건 찾음",
        "col_own_time": "내 시간", "col_partner_time": "상대 시간",
        "proposal_group": "제안 문구", "partner_label": "거래처",
        "language_label": "언어", "copy_button": "복사",
        "copied": "복사했습니다",
        "dlg_add": "거래처 추가", "dlg_edit": "거래처 편집",
        "f_name": "이름", "f_country": "국가", "f_city": "도시",
        "f_zone": "시간대", "f_lang": "제안 언어",
        "auto": "자동", "delete_confirm": "이 거래처를 삭제할까요?",
        "no_partners": "아직 등록된 거래처가 없습니다. 추가해 주세요.",
        "select_partner": "거래처를 선택하세요",
        "save": "저장", "cancel": "취소",
        "use_slot": "이 후보를 제안에 사용",
        "own_label": "나",
    },
}


def t(lang: str, key: str, **kw) -> str:
    """Translate *key* into *lang* (English fallback), then format."""
    text = STRINGS.get(lang, {}).get(key)
    if text is None:
        text = STRINGS["en"].get(key, key)
    if kw:
        text = text.format(**kw)
    return text


# ----------------------------------------------------------------------
# Meeting-proposal templates (one per language)
# ----------------------------------------------------------------------

PROPOSALS = {
    "ja": ("{name} ご担当者様\n\n"
           "会議の日程をご提案いたします。\n\n"
           "・相手側の時間：{partner_time}（{partner_city}）\n"
           "・当方の時間：{own_time}（{own_city}）\n\n"
           "ご都合がよろしければお知らせください。\n"
           "よろしくお願いいたします。"),
    "en": ("Dear {name} team,\n\n"
           "I would like to propose the following time for our meeting:\n\n"
           "- Your time: {partner_time} ({partner_city})\n"
           "- My time: {own_time} ({own_city})\n\n"
           "Please let me know if this works for you.\n"
           "Thank you very much."),
    "es": ("Estimado equipo de {name}:\n\n"
           "Me gustaría proponer el siguiente horario para nuestra reunión:\n\n"
           "- Su hora: {partner_time} ({partner_city})\n"
           "- Mi hora: {own_time} ({own_city})\n\n"
           "Por favor, avíseme si le conviene.\n"
           "Muchas gracias."),
    "zh": ("{name} 团队，您好：\n\n"
           "我想提议以下会议时间：\n\n"
           "- 贵方时间：{partner_time}（{partner_city}）\n"
           "- 我方时间：{own_time}（{own_city}）\n\n"
           "如该时间合适，请告知。\n"
           "非常感谢。"),
    "fr": ("Bonjour à l'équipe de {name},\n\n"
           "Je vous propose l'horaire suivant pour notre réunion :\n\n"
           "- Votre heure : {partner_time} ({partner_city})\n"
           "- Mon heure : {own_time} ({own_city})\n\n"
           "Merci de me dire si cela vous convient.\n"
           "Cordialement."),
    "de": ("Sehr geehrtes Team von {name},\n\n"
           "ich möchte Ihnen folgenden Termin für unser Gespräch vorschlagen:\n\n"
           "- Ihre Zeit: {partner_time} ({partner_city})\n"
           "- Meine Zeit: {own_time} ({own_city})\n\n"
           "Bitte teilen Sie mir mit, ob Ihnen dieser Termin passt.\n"
           "Vielen Dank."),
    "pt": ("Prezada equipe de {name},\n\n"
           "Gostaria de propor o seguinte horário para a nossa reunião:\n\n"
           "- O seu horário: {partner_time} ({partner_city})\n"
           "- O meu horário: {own_time} ({own_city})\n\n"
           "Por favor, avise-me se este horário lhe convém.\n"
           "Muito obrigado."),
    "ru": ("Уважаемая команда {name}!\n\n"
           "Предлагаю следующее время для нашей встречи:\n\n"
           "- Ваше время: {partner_time} ({partner_city})\n"
           "- Моё время: {own_time} ({own_city})\n\n"
           "Пожалуйста, сообщите, подходит ли вам это время.\n"
           "Большое спасибо."),
    "it": ("Gentile team di {name},\n\n"
           "Vorrei proporre il seguente orario per la nostra riunione:\n\n"
           "- Il vostro orario: {partner_time} ({partner_city})\n"
           "- Il mio orario: {own_time} ({own_city})\n\n"
           "Vi prego di farmi sapere se vi sta bene.\n"
           "Grazie mille."),
    "tr": ("Sayın {name} ekibi,\n\n"
           "Toplantımız için aşağıdaki zamanı önermek isterim:\n\n"
           "- Sizin saatiniz: {partner_time} ({partner_city})\n"
           "- Benim saatim: {own_time} ({own_city})\n\n"
           "Bu zaman size uygunsa lütfen bildirin.\n"
           "Çok teşekkür ederim."),
    "ar": ("فريق {name} المحترم،\n\n"
           "أود اقتراح الموعد التالي لاجتماعنا:\n\n"
           "- وقتكم: {partner_time} ({partner_city})\n"
           "- وقتي: {own_time} ({own_city})\n\n"
           "يرجى إعلامي إذا كان هذا الموعد مناسبًا لكم.\n"
           "شكرًا جزيلًا."),
    "id": ("Tim {name} yang terhormat,\n\n"
           "Saya ingin mengusulkan waktu berikut untuk pertemuan kita:\n\n"
           "- Waktu Anda: {partner_time} ({partner_city})\n"
           "- Waktu saya: {own_time} ({own_city})\n\n"
           "Mohon beri tahu saya jika waktu ini cocok untuk Anda.\n"
           "Terima kasih banyak."),
    "ko": ("{name} 담당자님께\n\n"
           "회의 일정으로 다음 시간을 제안드립니다.\n\n"
           "- 귀사 시간: {partner_time}({partner_city})\n"
           "- 당사 시간: {own_time}({own_city})\n\n"
           "가능하시면 알려 주시기 바랍니다.\n"
           "감사합니다."),
}


def proposal(lang: str, **kw) -> str:
    tpl = PROPOSALS.get(lang) or PROPOSALS["en"]
    return tpl.format(**kw)


# ----------------------------------------------------------------------
# Extra keys (input-error guidance) — merged into STRINGS above
# ----------------------------------------------------------------------

_EXTRA = {
    "ja": {"time_gap": "注意：その時刻は夏時間の切り替えで存在しません（時計が飛ぶ時間帯です）。別の時刻を選んでください。",
           "time_ambiguous": "注意：その時刻は夏時間の終了で2回あります（重なる時間帯です）。",
           "invalid_zone": "タイムゾーン名が正しくありません。"},
    "en": {"time_gap": "Note: that time does not exist (daylight-saving spring-forward gap). Please pick another time.",
           "time_ambiguous": "Note: that time occurs twice (daylight-saving fall-back overlap).",
           "invalid_zone": "That timezone name is not valid."},
    "es": {"time_gap": "Nota: esa hora no existe (salto por el horario de verano). Elija otra hora.",
           "time_ambiguous": "Nota: esa hora ocurre dos veces (solapamiento al terminar el horario de verano).",
           "invalid_zone": "Ese nombre de zona horaria no es válido."},
    "zh": {"time_gap": "注意：该时间不存在（夏令时向前跳过的时段）。请选择其他时间。",
           "time_ambiguous": "注意：该时间会出现两次（夏令时结束时的重叠时段）。",
           "invalid_zone": "时区名称无效。"},
    "fr": {"time_gap": "Remarque : cette heure n'existe pas (saut de l'heure d'été). Choisissez une autre heure.",
           "time_ambiguous": "Remarque : cette heure se produit deux fois (chevauchement à la fin de l'heure d'été).",
           "invalid_zone": "Ce nom de fuseau horaire n'est pas valide."},
    "de": {"time_gap": "Hinweis: Diese Uhrzeit existiert nicht (Sprung bei der Zeitumstellung). Bitte wählen Sie eine andere Zeit.",
           "time_ambiguous": "Hinweis: Diese Uhrzeit kommt zweimal vor (Überschneidung bei der Zeitumstellung).",
           "invalid_zone": "Dieser Zeitzonenname ist ungültig."},
    "pt": {"time_gap": "Nota: essa hora não existe (salto do horário de verão). Escolha outra hora.",
           "time_ambiguous": "Nota: essa hora ocorre duas vezes (sobreposição no fim do horário de verão).",
           "invalid_zone": "Esse nome de fuso horário não é válido."},
    "ru": {"time_gap": "Примечание: такого времени не существует (пропуск при переходе на летнее время). Выберите другое время.",
           "time_ambiguous": "Примечание: это время встречается дважды (перекрытие при переходе на зимнее время).",
           "invalid_zone": "Недопустимое название часового пояса."},
    "it": {"time_gap": "Nota: quell'ora non esiste (salto dell'ora legale). Scegli un'altra ora.",
           "time_ambiguous": "Nota: quell'ora si verifica due volte (sovrapposizione alla fine dell'ora legale).",
           "invalid_zone": "Nome del fuso orario non valido."},
    "tr": {"time_gap": "Not: Bu saat mevcut değil (yaz saati ileri alma boşluğu). Lütfen başka bir saat seçin.",
           "time_ambiguous": "Not: Bu saat iki kez gerçekleşiyor (yaz saati geri alma çakışması).",
           "invalid_zone": "Bu saat dilimi adı geçerli değil."},
    "ar": {"time_gap": "ملاحظة: هذا الوقت غير موجود (فجوة الانتقال إلى التوقيت الصيفي). يرجى اختيار وقت آخر.",
           "time_ambiguous": "ملاحظة: هذا الوقت يحدث مرتين (تداخل نهاية التوقيت الصيفي).",
           "invalid_zone": "اسم المنطقة الزمنية غير صالح."},
    "id": {"time_gap": "Catatan: waktu itu tidak ada (lompatan waktu musim panas). Silakan pilih waktu lain.",
           "time_ambiguous": "Catatan: waktu itu terjadi dua kali (tumpang tindih akhir waktu musim panas).",
           "invalid_zone": "Nama zona waktu tidak valid."},
    "ko": {"time_gap": "참고: 그 시각은 존재하지 않습니다(서머타임 시작 시 건너뛰는 시간대). 다른 시각을 선택하세요.",
           "time_ambiguous": "참고: 그 시각은 두 번 있습니다(서머타임 종료 시 겹치는 시간대).",
           "invalid_zone": "시간대 이름이 올바르지 않습니다."},
}
for _lang, _kv in _EXTRA.items():
    STRINGS.setdefault(_lang, {}).update(_kv)


# ----------------------------------------------------------------------
# Extra keys (theme toggle button) — merged into STRINGS above
# ----------------------------------------------------------------------

_EXTRA_THEME = {
    "ja": {"theme_button": "画面テーマを切り替える（ダーク／ライト）",
           "theme_dark": "ダーク", "theme_light": "ライト"},
    "en": {"theme_button": "Switch the display theme (dark / light)",
           "theme_dark": "Dark", "theme_light": "Light"},
    "es": {"theme_button": "Cambiar el tema de pantalla (oscuro / claro)",
           "theme_dark": "Oscuro", "theme_light": "Claro"},
    "zh": {"theme_button": "切换显示主题（深色/浅色）",
           "theme_dark": "深色", "theme_light": "浅色"},
    "fr": {"theme_button": "Changer le thème d'affichage (sombre / clair)",
           "theme_dark": "Sombre", "theme_light": "Clair"},
    "de": {"theme_button": "Anzeigethema wechseln (dunkel / hell)",
           "theme_dark": "Dunkel", "theme_light": "Hell"},
    "pt": {"theme_button": "Alternar o tema de exibição (escuro / claro)",
           "theme_dark": "Escuro", "theme_light": "Claro"},
    "ru": {"theme_button": "Переключить тему оформления (тёмная / светлая)",
           "theme_dark": "Тёмная", "theme_light": "Светлая"},
    "it": {"theme_button": "Cambia tema di visualizzazione (scuro / chiaro)",
           "theme_dark": "Scuro", "theme_light": "Chiaro"},
    "tr": {"theme_button": "Görünüm temasını değiştir (koyu / açık)",
           "theme_dark": "Koyu", "theme_light": "Açık"},
    "ar": {"theme_button": "تبديل سمة العرض (داكنة / فاتحة)",
           "theme_dark": "داكنة", "theme_light": "فاتحة"},
    "id": {"theme_button": "Ganti tema tampilan (gelap / terang)",
           "theme_dark": "Gelap", "theme_light": "Terang"},
    "ko": {"theme_button": "화면 테마 전환(다크/라이트)",
           "theme_dark": "다크", "theme_light": "라이트"},
}
for _lang, _kv in _EXTRA_THEME.items():
    STRINGS.setdefault(_lang, {}).update(_kv)


# ----------------------------------------------------------------------
# Locale-correct date/time formatting via Babel
# ----------------------------------------------------------------------

BABEL_LOCALES = {
    "ja": "ja_JP", "en": "en_US", "es": "es", "zh": "zh_Hans_CN",
    "fr": "fr", "de": "de", "pt": "pt", "ru": "ru", "it": "it",
    "tr": "tr", "ar": "ar", "id": "id", "ko": "ko",
}

try:
    from babel.dates import format_datetime as _babel_fmt
except Exception:  # pragma: no cover - Babel is a hard dependency
    _babel_fmt = None


def _fmt(dt, pattern, lang):
    if _babel_fmt is not None:
        try:
            return _babel_fmt(dt, pattern,
                              locale=BABEL_LOCALES.get(lang, "en_US"))
        except Exception:
            pass
    return dt.strftime("%Y-%m-%d (%a) %H:%M")


def fmt_datetime(dt, lang) -> str:
    """'2026-01-19 (Mon) 17:00' with the weekday in the UI language."""
    return _fmt(dt, "yyyy-MM-dd (EEE) HH:mm", lang)


def fmt_date(dt, lang) -> str:
    return _fmt(dt, "yyyy-MM-dd (EEE)", lang)


def fmt_chip(dt, lang) -> str:
    return _fmt(dt, "MM-dd (EEE) HH:mm", lang)
