import requests
import signal
from contextlib import contextmanager
from datetime import datetime
import json
import time
import os
import sys
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPM
import PySimpleGUI
import re
from hashlib import sha256

API = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/calendarByDistrict"
API_BOOK = "https://cdn-api.co-vin.in/api/v2/appointment/schedule"
CAPTCHA_URL = "https://cdn-api.co-vin.in/api/v2/auth/getRecaptcha"

DISTRICT = 'district_id'
DATE = 'date'
BENEFICIARY = ''
DISTRICT_ID = '188'
# Looking slots in Gurgaon
VACCINE_PREFERENCE = ['COVAXIN']
# VACCINE_PREFERENCE = ['COVAXIN', 'COVISHIELD']

QUERY_PARAMS = {DISTRICT: DISTRICT_ID, DATE: datetime.now().date().strftime("%d-%m-%Y")}

BROWSER_HEADERS = [{'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.76 Safari/537.36'},
                   {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'}]


@contextmanager
def timeout(time):
    # Register a function to raise a TimeoutError on the signal.
    signal.signal(signal.SIGALRM, raise_timeout)
    # Schedule the signal to be sent after ``time``.
    signal.alarm(time)
    try:
        yield
    except TimeoutError:
        pass
    finally:
        # Unregister the signal so it won't be triggered
        # if the timeout is not reached.
        signal.signal(signal.SIGALRM, signal.SIG_IGN)


def raise_timeout(signum, frame):
    raise TimeoutError


def find_sessions(headers):
    url = get_url_with_query_params()
    response = None
    booked = False
    try:
        with timeout(10):
            response = requests.get(url, headers=BROWSER_HEADERS[1])
    except Exception as e:
        print('Not getting correct response from api in specified time', e)

    if response and response.status_code == 200 and ('centers' in json.loads(response.text)):
        centers = json.loads(response.text)['centers']
        found = False
        for center in centers:
            for session in center['sessions']:
                if session['min_age_limit'] == 18 and session['available_capacity'] > 0 and session['available_capacity_dose1'] > 0:
                    print('******', center['name'], session['date'], session['vaccine'], session['available_capacity'], session['available_capacity_dose1'])
                    found = True
        if found:
            os.system('echo -e "\a"')
        for center in centers:
            for session in center['sessions']:
                if session['min_age_limit'] == 18 and session['available_capacity'] > 0 and session['available_capacity_dose1'] > 0 and session['vaccine'] in VACCINE_PREFERENCE:
                    data = {"center_id": center['center_id'], "session_id": session['session_id'],
                            "beneficiaries":[BENEFICIARY], "slot": session['slots'][1],
                            "captcha": "nMReQ", "dose": 1}
                    data['captcha'] = generate_captcha(headers)
                    book_response = requests.post(API_BOOK, data=json.dumps(data), headers=headers)
                    booked = True if book_response.status_code in [200, 201] else False
                    print(book_response.status_code)
                    print(book_response.text)
                    found = True
        print('******No slot available in centers: ', len(centers)) if not found else None
    return not booked


def captcha_builder(resp):
    with open('captcha.svg', 'w') as f:
        f.write(re.sub('(<path d=)(.*?)(fill=\"none\"/>)', '', resp['captcha']))

    drawing = svg2rlg('captcha.svg')
    renderPM.drawToFile(drawing, "captcha.png", fmt="PNG")

    layout = [[PySimpleGUI.Image('captcha.png')],
              [PySimpleGUI.Text("Enter Captcha Below")],
              [PySimpleGUI.Input(key='inp')],
              [PySimpleGUI.Button('Submit', bind_return_key=True)]]

    window = PySimpleGUI.Window('Enter Captcha', layout, finalize=True)
    window.TKroot.focus_force()         # focus on window
    window.Element('inp').SetFocus()    # focus on field
    event, values = window.read()
    window.close()
    return values['inp']


def generate_captcha(request_header):
    print('================================= GETTING CAPTCHA ==================================================')
    resp = requests.post(CAPTCHA_URL, headers=request_header)
    print("Captcha Response Code: ", resp.status_code)

    if resp.status_code == 200:
        return captcha_builder(resp.json())


def get_url_with_query_params():
    query_params_url = ''
    for param in QUERY_PARAMS:
        query_params_url = query_params_url + param + '=' + QUERY_PARAMS[param] + '&'
    if query_params_url:
        query_params_url = '?' + query_params_url[:-1]
    url = API + query_params_url
    return url


def generate_token_otp():
    """
    This function generate OTP and returns a new token
    """
    mobile = input("Enter the registered mobile number: ")
    headers = BROWSER_HEADERS[1]

    valid_token = False
    while not valid_token:
        try:
            data = {"mobile": mobile,
                    "secret": "U2FsdGVkX1+z/4Nr9nta+2DrVJSv7KS6VoQUSQ1ZXYDx/CJUkWxFYG6P3iM/VW+6jLQ9RDQVzp/RcZ8kbT41xw=="
            }
            transaction_id = requests.post(
                url='https://cdn-api.co-vin.in/api/v2/auth/generateMobileOTP', json=data, headers=headers
            )

            if transaction_id.status_code == 200:
                print("Successfully requested OTP for mobile number")
                transaction_id = transaction_id.json()['txnId']

                OTP = input("Enter OTP (If this takes more than 2 minutes, press Enter to retry): ")
                if OTP:
                    data = {"otp": sha256(str(OTP).encode('utf-8')).hexdigest(), "txnId": transaction_id}
                    print("Validating OTP..")

                    token = requests.post(url='https://cdn-api.co-vin.in/api/v2/auth/validateMobileOtp', json=data,
                                          headers=headers)
                    if token.status_code == 200:
                        token = token.json()['token']
                        print('Token Generated')
                        valid_token = True
                        return token

                    else:
                        print('Unable to Validate OTP')
                        print("Response: ", token.text)

                        retry = input("Retry ? (y/n Default y): ")
                        retry = retry if retry else 'y'
                        if retry == 'y':
                            pass
                        else:
                            sys.exit()

            else:
                print('Unable to Generate OTP')
                print(transaction_id.status_code, transaction_id.text)

                retry = input("Retry ? (y/n Default y): ")
                retry = retry if retry else 'y'
                if retry == 'y':
                    pass
                else:
                    sys.exit()

        except Exception as e:
            print(str(e))


def main():
    if BENEFICIARY and DISTRICT_ID:
        generate_token = input("Generate New Token?, Press n if you ran the script in last 10 min (y/n Default y): ")
        generate_token = generate_token if generate_token else 'y'
        if generate_token == 'y':
            token = generate_token_otp()
            os.system("sed -i -s 's/existing_token = [\"*]/existing_token = \"{new_token}/g' {file}".format(
                new_token=token, file='./book_vaccination.py'
            ))
            os.system('rm ./book_vaccination.py-s')
        else:
            existing_token = ""
            token = existing_token
        if token:
            keep_looking = True
            headers = BROWSER_HEADERS[1]
            headers['Authorization'] = 'Bearer ' + token
            while keep_looking:
                keep_looking = find_sessions(headers)
                time.sleep(0.5)
        else:
            print("Please generate Token")
    else:
        print("Enter beneficiary ID and district ID")


if __name__ == '__main__':
    main()
