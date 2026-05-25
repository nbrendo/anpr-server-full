import hashlib
from typing import Dict


FIRST_NAMES = [
    "Tendai",
    "Ruvimbo",
    "Farai",
    "Nyasha",
    "Tinashe",
    "Memory",
    "Blessing",
    "Kudakwashe",
    "Chipo",
    "Munyaradzi",
]

LAST_NAMES = [
    "Moyo",
    "Dube",
    "Ndlovu",
    "Sibanda",
    "Madziva",
    "Chirau",
    "Machingura",
    "Maposa",
    "Gumbo",
    "Makwanya",
]

CITIES = [
    "Harare",
    "Bulawayo",
    "Mutare",
    "Gweru",
    "Masvingo",
    "Kwekwe",
    "Chinhoyi",
    "Bindura",
]

OWNER_TYPES = ["Private", "Company", "Government", "School", "Taxi Operator"]


def demo_owner_for_plate(plate: str) -> Dict[str, str]:
    seed = int(hashlib.sha256(plate.encode("utf-8")).hexdigest()[:12], 16)
    first = FIRST_NAMES[seed % len(FIRST_NAMES)]
    last = LAST_NAMES[(seed // 7) % len(LAST_NAMES)]
    city = CITIES[(seed // 13) % len(CITIES)]
    owner_type = OWNER_TYPES[(seed // 17) % len(OWNER_TYPES)]
    reg_no = f"ZIM-{seed % 900000 + 100000}"

    return {
        "registered": "YES",
        "owner_name": f"{first} {last}",
        "owner_type": owner_type,
        "owner_city": city,
        "registration_number": reg_no,
        "data_source": "Demo registry",
    }
