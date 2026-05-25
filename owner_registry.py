import hashlib
from typing import Dict, Optional

# Demo data for generating realistic owner information
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
    "Takudzwa",
    "Ruvarashe",
    "Anotida",
    "Tafadzwa",
    "Kundai",
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
    "Chikumbirike",
    "Makoni",
    "Mutasa",
    "Chigumbura",
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
    "Marondera",
    "Victoria Falls",
]

OWNER_TYPES = ["Private", "Company", "Government", "School", "Taxi Operator", "Fleet Management"]


def demo_owner_for_plate(plate: str) -> Dict[str, str]:
    """
    Generate demo owner information based on plate number.
    
    This is a deterministic function that always returns the same owner
    for the same plate number, making it useful for demo purposes.
    
    Args:
        plate: License plate number (e.g., "ABC 1234")
    
    Returns:
        Dictionary containing owner information
    """
    # Create a deterministic hash from the plate number
    seed = int(hashlib.sha256(plate.encode("utf-8")).hexdigest()[:12], 16)
    
    # Generate owner details based on the seed
    first = FIRST_NAMES[seed % len(FIRST_NAMES)]
    last = LAST_NAMES[(seed // 7) % len(LAST_NAMES)]
    city = CITIES[(seed // 13) % len(CITIES)]
    owner_type = OWNER_TYPES[(seed // 17) % len(OWNER_TYPES)]
    reg_no = f"ZIM-{seed % 900000 + 100000}"
    
    # Special handling for blacklisted plates (example)
    blacklisted_plates = ["AGG 7148", "ABC 1234", "ADE 3450", "AGC 4483"]
    if plate in blacklisted_plates:
        owner_type = "Blacklisted"
        return {
            "registered": "NO",
            "owner_name": "BLACKLISTED VEHICLE",
            "owner_type": owner_type,
            "owner_city": "Unknown",
            "registration_number": "SUSPENDED",
            "data_source": "Demo registry",
            "status": "ALERT - Blacklisted vehicle detected!",
        }
    
    # Return standard owner information
    return {
        "registered": "YES",
        "owner_name": f"{first} {last}",
        "owner_type": owner_type,
        "owner_city": city,
        "registration_number": reg_no,
        "data_source": "Demo registry",
        "status": "Normal",
    }


def get_owner_by_plate(plate: str) -> Optional[Dict[str, str]]:
    """
    Public interface to get owner information by plate number.
    
    Args:
        plate: License plate number
    
    Returns:
        Owner information dictionary or None if not found
    """
    try:
        return demo_owner_for_plate(plate)
    except Exception as e:
        print(f"Error retrieving owner for plate {plate}: {e}")
        return None


def validate_plate_registration(plate: str) -> bool:
    """
    Check if a plate is registered in the demo system.
    
    Args:
        plate: License plate number
    
    Returns:
        True if registered, False otherwise
    """
    owner_info = get_owner_by_plate(plate)
    if owner_info and owner_info.get("registered") == "YES":
        return True
    return False


# For testing and debugging
if __name__ == "__main__":
    # Test the registry with some sample plates
    test_plates = ["ABC 1234", "DEF 5678", "AGG 7148", "XYZ 9999"]
    
    print("Testing Owner Registry:")
    print("=" * 50)
    
    for plate in test_plates:
        owner = demo_owner_for_plate(plate)
        print(f"\nPlate: {plate}")
        print(f"  Owner: {owner.get('owner_name')}")
        print(f"  Type: {owner.get('owner_type')}")
        print(f"  City: {owner.get('owner_city')}")
        print(f"  Registration: {owner.get('registration_number')}")
        print(f"  Registered: {owner.get('registered')}")
        if owner.get('status') == "ALERT - Blacklisted vehicle detected!":
            print(f"  ⚠️  {owner.get('status')}")