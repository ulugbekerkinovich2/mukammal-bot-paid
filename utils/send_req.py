import requests
from pprint import pprint
def check_number(phone):

    url = 'https://crmapi.mentalaba.uz/v1/auth/check'

    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        'origin': 'https://admission.mentalaba.uz'
    }

    data = {
        "phone": phone
    }

    response = requests.post(url, headers=headers, json=data)  # Include the headers here
    # print(response.json())
    # print(response.status_code)
    # print(response.json())
    return response
check_number('+998942559015')


def user_register(number):
    url = "https://crmapi.mentalaba.uz/v1/auth/register"
    headers = {
        'accept': 'application/json', 
        'Content-Type': 'application/json',
        'origin': 'admission.mentalaba.uz'
    }
    body = {
        "phone": number
    }
    response = requests.post(url, json=body, headers=headers)
    fake_obj = {
        'status': 201
    }
    # if response.status_code == 201:
        # pprint(response.json(),'\n\n')
    return fake_obj

# user_register('+998998359015')

def user_verify(secret_code, phone):
    url = "https://crmapi.mentalaba.uz/v1/auth/verify"
    headers = {
        'accept': 'application/json', 
        'Content-Type': 'application/json',
        'origin': 'admission.mentalaba.uz'
    }
    body = {
        'phone' : phone,
        "code": secret_code
    }
    response = requests.post(url, json=body, headers=headers)

    # pprint(response.json())
    return response.json()
    
# user_verify(793811, '+998335015711')

def user_login(phone):
    url = "https://crmapi.mentalaba.uz/v1/auth/login"
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        'origin': 'admission.mentalaba.uz'
    }
    body = {
        'phone': phone
    }
    response = requests.post(url, json=body, headers=headers)
    # print(response.status_code)
    # pprint(response.json())
    fake_obj = {
        'status': 201
    }
    return fake_obj
# user_login('+998942559015')

def application_form(birth_date, document, token):
    url = 'https://crmapi.mentalaba.uz/v1/application-forms/info'

    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        'origin': 'admission.mentalaba.uz',
        'Authorization': f'Bearer {token}'
    }
    body = {
        'birth_date': birth_date,
        'document': document
    }
    response = requests.post(url, json=body, headers=headers)
    # pprint(response.json())
    return response.json()

def directions(token):
    url = 'https://crmapi.mentalaba.uz/v1/directions'
    headers = {
        'accept': 'application/json', 
        'Content-Type': 'application/json',
        'origin': 'admission.mentalaba.uz',
        'Authorization': f'Bearer {token}'
    }
    response = requests.get(url, headers=headers)
    return response.json()

def applicants(token, degree_id, direction_id, education_language_id, education_type_id):
    url = "https://crmapi.mentalaba.uz/v1/applicants"
    headers = {
        'accept': 'application/json', 
        'Content-Type': 'application/json',
        'origin': 'admission.mentalaba.uz',
        'Authorization': f"Bearer {token}"
    }
    body = {
        'degree_id': degree_id,
        'direction_id': direction_id,
        'education_language_id': education_language_id,
        'education_type_id': education_type_id
    }
    response = requests.post(url, json=body, headers=headers)
    return response.json()




