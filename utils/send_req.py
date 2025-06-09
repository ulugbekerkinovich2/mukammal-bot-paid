import aiohttp
from data.config import main_url
from icecream import ic
async def auth_check(phone):
    url = f"{main_url}/v1/auth/check"
    payload = {
        "phone": phone
    }
    headers = {
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            return await response.text()


async def user_register(phone, password):
    url = f"{main_url}/v2/auth/register"
    payload = {
        "phone": phone,
        "password": password
    }
    headers = {
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_

async def user_verify(phone, code):
    url = f"{main_url}/v2/auth/verify"
    payload = {
        "code": code,
        "phone": phone
    }
    headers = {
        "Content-Type": "application/json"
    }
    # print(payload)
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        
    
async def user_info(birth_date, document, token):
    url = f"{main_url}/v1/info"
    
    payload = {
        "birth_date": birth_date,
        "browser_name": "Telegram",
        "device_name": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "document": document,
        "ip_address": "45.150.24.19"
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Referer": "https://mentalaba.uz/",
        "Origin": "https://mentalaba.uz"
    }
    print(headers)
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        

async def user_login(phone, password):
    url = f"{main_url}/v1/auth/user/login"
    payload = {
        "phone": phone,
        "password": password
    }
    headers = {
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        
    
async def delete_user(token, phone, password):
    url = f"{main_url}/v1/users/delete-account"
    payload = {
        "phone": phone,
        "password": password
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    ic(headers, payload)

    async with aiohttp.ClientSession() as session:
        async with session.delete(url, json=payload, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        


async def upload_image(token, image_path):
    url = f"{main_url}/v1/images/upload"

    headers = {
        "Authorization": f"Bearer {token}"
        # Content-Type'ni yozmang — aiohttp o'zi qo'shadi!
    }

    form = aiohttp.FormData()
    form.add_field("associated_with", "users")
    form.add_field("usage", "avatar")
    form.add_field(
        "file",
        open(image_path, "rb"),
        filename="avatar.png",
        content_type="image/png"
    )

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=form, headers=headers) as response:
            status_ = response.status
            response_json = await response.json()
            return response_json, status_


import aiohttp

async def upload_file(token, image_path):
    url = f"{main_url}/v1/images/upload"

    headers = {
        "Authorization": f"Bearer {token}"
        # Content-Type yozilmaydi, aiohttp FormData uchun o'zi qo'shadi
    }

    form = aiohttp.FormData()
    form.add_field("associated_with", "users")
    form.add_field("usage", "diploma")

    with open(image_path, "rb") as f:
        form.add_field(
            "file",
            f,
            filename="diploma.png"  # kerak bo'lsa dinamik o'zgartiring
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form, headers=headers) as response:
                status_ = response.status
                response_json = await response.json()
                return response_json, status_


async def fetch_regions(token):
    url = f"{main_url}/v1/locations/regions?status=active"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
    

async def fetch_educations(token):
    url =f"{main_url}/v1/education-types/educations"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        
async def district_locations(id, token):
    url = f"{main_url}/v1/locations/districts/{id}"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        
async def me(token):
    url = f"{main_url}/v1/application-form/me"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        
async def update_application_form(token, district_id, region_id, institution_name, graduation_year, file_path):
    url = f"{main_url}/v1/application-form"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "update_required_section": "having_problem_with_education",
        "user_education": {
            "country_id": 234,
            "district_id": district_id,
            "education_type": "1",
            "file": [file_path],
            "graduation_year": graduation_year,
            "institution_name": institution_name,
            "region_id": region_id,
            "src": "manually"
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.patch(url, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_