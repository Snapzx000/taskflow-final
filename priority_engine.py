from datetime import datetime, timedelta

def calculate_priority(description, deadline):
    now = datetime.utcnow()
    delta = deadline - now
    
    # Base level from deadline
    if delta < timedelta(days=3):
        level = 'high'
    elif delta < timedelta(days=7):
        level = 'medium'
    else:
        level = 'low'

    # Adjust from keywords
    desc_lower = description.lower()
    if 'urgent' in desc_lower or 'emergency' in desc_lower:
        level = 'high'
    elif 'important' in desc_lower:
        level = 'medium' if level == 'low' else level

    return level