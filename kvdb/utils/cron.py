"""
Cron Utils
"""

import re
import croniter

_time_aliases_groups = {
    'seconds': ['s', 'sec', 'secs'],
    'minutes': ['m', 'min', 'mins'],
    'hours': ['h', 'hr', 'hrs'],
    'days': ['d', 'day'],
    'weeks': ['w', 'wk', 'wks'],
    'months': ['mo', 'mon', 'mons'],
}
_time_aliases = {alias: unit for unit, aliases in _time_aliases_groups.items() for alias in aliases}
_time_pattern = re.compile(r'(?:(?:every )?(\d+) (\w+))(?:, | and )?')

def validate_cron_schedule(cron_schedule: str) -> str:
    """
    Convert natural language to cron format using regex patterns

    Examples:
    - 'every 5 minutes'
    - 'every 10 minutes'
    - 'every 5 hrs'
    """
    if croniter.croniter.is_valid(cron_schedule): return cron_schedule
    time_units = {
        'seconds': None,
        'minutes': '*',
        'hours': '*',
        'days': '*',
        'weeks': '*',
        'months': '*'
    }
    time_values = {
        'seconds': None,
        'minutes': 0,
        'hours': 0,
        'days': 0,
        'weeks': 0,
        'months': 0
    }
    match = _time_pattern.findall(cron_schedule)
    if not match: raise ValueError(f"Invalid cron expression: {cron_schedule}")

    for num, unit in match:
        if unit in _time_aliases: unit = _time_aliases[unit]
        if not unit.endswith('s'): unit += 's'
        if unit not in time_units:
            raise ValueError(f"Invalid time unit in cron expression: unit: {unit}, num: {num}")
        time_values[unit] = int(num)
        # time_units[unit] = f'*/{num}'
    
    # Handle overflow units
    if time_values['seconds'] and time_values['seconds'] >= 60:
        time_values['minutes'] += time_values['seconds'] // 60
        time_values['seconds'] = time_values['seconds'] % 60
    if time_values['minutes'] >= 60:
        time_values['hours'] += time_values['minutes'] // 60
        time_values['minutes'] = time_values['minutes'] % 60
    if time_values['hours'] >= 24:
        time_values['days'] += time_values['hours'] // 24
        time_values['hours'] = time_values['hours'] % 24
    if time_values['days'] >= 7:
        time_values['weeks'] += time_values['days'] // 7
        time_values['days'] = time_values['days'] % 7
    if time_values['weeks'] >= 4:
        time_values['months'] += time_values['weeks'] // 4
        time_values['weeks'] = time_values['weeks'] % 4
    
    for unit in time_units:
        if time_values[unit]:
            time_units[unit] = f'*/{time_values[unit]}'
    
    # Handle overflow units
    if time_units['hours'] != "*" and time_units['minutes'] == '*':
        time_units['minutes'] = 0
    if time_units['days'] != "*" and time_units['hours'] == '*':
        time_units['hours'] = 0
    if time_units['weeks'] != "*" and time_units['days'] == '*':
        time_units['days'] = 0
    if time_units['months'] != "*" and time_units['weeks'] == '*':
        time_units['weeks'] = 0
    
    cron_expression = f"{time_units['minutes']} {time_units['hours']} {time_units['days']} {time_units['months']} {time_units['weeks']}"
    if time_units['seconds']:
        cron_expression += f" {time_units['seconds']}"
    return cron_expression.strip()


