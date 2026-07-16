# Sample code with intentional issues for the agent to find during your demo

import os

password = "admin123"  # hardcoded secret - bad!

def process_items(items, cache=[]):  # mutable default argument - bad!
    for item in items:
        cache.append(item)
    return cache

def run_user_code(user_input):
    try:
        result = eval(user_input)  # security risk - bad!
        return result
    except:  # bare except - bad!
        pass

def get_user_data(user_id):
    # TODO: add real database lookup
    return {"id": user_id, "name": "placeholder"}
