DEFAULT_PROFILE = {
    "desired_role": "",
    "work_formats": [],
    "locations": [],
    "locations_any": False,
    "min_salary": None,
    "experience": None,
    "skills": [],
    "stop_words": [],
    "blacklisted_companies": [],
}

WORK_FORMAT_OPTIONS = ["Удалёнка", "Гибрид", "Офис"]
LOCATION_OPTIONS = [
    "Москва",
    "Санкт-Петербург",
    "Новосибирск",
    "Екатеринбург",
    "Казань",
    "Нижний Новгород",
    "Самара",
    "Ростов-на-Дону",
    "Уфа",
    "Краснодар",
    "Воронеж",
    "Пермь",
    "Челябинск",
    "Омск",
    "Волгоград",
    "Владивосток",
    "Не важно",
]
EXPERIENCE_OPTIONS = ["Нет опыта", "1-3 года", "3-6 лет", "6+ лет"]

STEPS = [
    "desired_role",
    "work_format",
    "locations",
    "min_salary",
    "experience",
    "skills",
    "stop_words",
    "blacklisted_companies",
]

vacancy_cache: dict[int, dict] = {}
seen_vacancies: dict[int, set[str]] = {}
last_fetch_info: dict[int, dict] = {}
user_state: dict[int, dict] = {}
profiles: dict[int, dict] = {}
