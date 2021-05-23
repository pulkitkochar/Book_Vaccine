import requests
import signal
from contextlib import contextmanager
from datetime import datetime
import json
import tabulate
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


def find_sessions(headers, district_id, vaccine_preference, beneficiary_ids, center_preference, captcha):
    url = get_url_with_query_params(district_id)
    response = None
    booked = False
    doses = len(beneficiary_ids)
    try:
        with timeout(10):
            response = requests.get(url, headers=headers)
    except Exception as e:
        print('Not getting correct response from api in specified time', e)

    if response and response.status_code == 200 and ('centers' in json.loads(response.text)):
        centers = json.loads(response.text)['centers']
        found = False
        for center in centers:
            for session in center['sessions']:
                if session['min_age_limit'] == 18 and session['available_capacity'] >= doses and session['available_capacity_dose1'] >= doses:
                    print('******', center['name'], session['date'], session['vaccine'], session['available_capacity'], session['available_capacity_dose1'])
                    found = True
                    os.system('echo -e "\a"')
                    if (not vaccine_preference or session['vaccine'] == vaccine_preference) and (not center_preference or center_preference.lower() in center['name'].lower()):
                        data = {'center_id': center['center_id'], 'session_id': session['session_id'],
                                'beneficiaries': beneficiary_ids, 'slot': session['slots'][-1], 'captcha': 'nMReQ',
                                'dose': 1}
                        data['captcha'] = captcha
                        book_response = requests.post(API_BOOK, data=json.dumps(data), headers=headers)
                        booked = True if book_response.status_code in [200, 201] else False
                        print(book_response.status_code)
                        print(book_response.text)
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


def get_url_with_query_params(district_id):
    params = {DISTRICT: district_id, DATE: datetime.now().date().strftime("%d-%m-%Y")}
    query_params_url = ''
    for param in params:
        query_params_url = query_params_url + param + '=' + params[param] + '&'
    if query_params_url:
        query_params_url = '?' + query_params_url[:-1]
    url = API + query_params_url
    return url


def generate_token_otp():
    """
    This function generate OTP and returns a new token
    """
    mobile = input("Enter the registered mobile number: ")
    headers = BROWSER_HEADERS[0]

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


def get_vaccine_preference():
    print("It seems you're trying to find a slot for your first dose. Do you have a vaccine preference?")
    preference = input("Enter 0 for No Preference, 1 for COVISHIELD, 2 for COVAXIN, Default 0 : ")
    preference = int(preference) if preference and int(preference) in [0, 1, 2] else 0

    if preference == 1:
        return 'COVISHIELD'
    elif preference == 2:
        return 'COVAXIN'
    else:
        return None


def display_table(dict_list):
    header = ['idx'] + list(dict_list[0].keys())
    rows = [[idx + 1] + list(x.values()) for idx, x in enumerate(dict_list)]
    print(tabulate.tabulate(rows, header, tablefmt='grid'))


def get_districts(header):
    states = requests.get('https://cdn-api.co-vin.in/api/v2/admin/location/states', headers=header)

    if states.status_code == 200:
        states = states.json()['states']

        refined_states = []
        for state in states:
            tmp = {'state': state['state_name']}
            refined_states.append(tmp)

        display_table(refined_states)
        state = int(input('\nEnter State index: '))
        state_id = states[state - 1]['state_id']
        district_url = 'https://cdn-api.co-vin.in/api/v2/admin/location/districts/' + str(state_id)

        districts = requests.get(district_url, headers=header)

        if districts.status_code == 200:
            districts = districts.json()['districts']

            refined_districts = []
            for district in districts:
                tmp = {'district': district['district_name']}
                refined_districts.append(tmp)

            display_table(refined_districts)
            reqd_districts = input('\nEnter index number of district to monitor : ')
            districts_idx = [int(idx) - 1 for idx in reqd_districts.split(',')]
            reqd_districts = [{
                'district_id': item['district_id'],
                'district_name': item['district_name'],
                'alert_freq': 440 + ((2 * idx) * 110)
            } for idx, item in enumerate(districts) if idx in districts_idx]

            print(f'Selected districts: ')
            display_table(reqd_districts)
            return reqd_districts

        else:
            print('Unable to fetch districts')
            print(districts.status_code)
            print(districts.text)
            sys.exit(1)

    else:
        print('Unable to fetch states')
        print(states.status_code)
        print(states.text)
        sys.exit(1)


def get_beneficiaries(request_header):
    beneficiaries = requests.get("https://cdn-api.co-vin.in/api/v2/appointment/beneficiaries", headers=request_header)

    if beneficiaries.status_code == 200:
        beneficiaries = beneficiaries.json()['beneficiaries']

        refined_beneficiaries = []
        for beneficiary in beneficiaries:
            beneficiary['age'] = datetime.today().year - int(beneficiary['birth_year'])

            tmp = {
                'bref_id': beneficiary['beneficiary_reference_id'],
                'name': beneficiary['name'],
                'vaccine': beneficiary['vaccine'],
                'age': beneficiary['age'],
                'status': beneficiary['vaccination_status']
            }
            refined_beneficiaries.append(tmp)

        display_table(refined_beneficiaries)

        print("""
        ################# IMPORTANT NOTES #################
        # 1. While selecting beneficiaries, make sure that selected beneficiaries are all taking the same dose: either first OR second.
        #    Please do no try to club together booking for first dose for one beneficiary and second dose for another beneficiary.
        #
        # 2. While selecting beneficiaries, also make sure that beneficiaries selected for second dose are all taking the same vaccine: COVISHIELD OR COVAXIN.
        #    Please do no try to club together booking for beneficiary taking COVISHIELD with beneficiary taking COVAXIN.
        #
        # 3. If you're selecting multiple beneficiaries, make sure all are of the same age group (45+ or 18+) as defined by the govt.
        #    Please do not try to club together booking for younger and older beneficiaries.
        ###################################################
        """)
        reqd_beneficiaries = input('Enter comma separated index numbers of beneficiaries to book for : ')
        beneficiary_idx = [int(idx) - 1 for idx in reqd_beneficiaries.split(',')]
        reqd_beneficiaries = [{
            'bref_id': item['beneficiary_reference_id'],
            'name': item['name'],
            'vaccine': item['vaccine'],
            'age': item['age'],
            'status': item['vaccination_status']
        } for idx, item in enumerate(beneficiaries) if idx in beneficiary_idx]

        print(f'Selected beneficiaries: ')
        display_table(reqd_beneficiaries)
        return reqd_beneficiaries

    else:
        print('Unable to fetch beneficiaries')
        print(beneficiaries.status_code)
        print(beneficiaries.text)
        return []


def get_center_preference():
    preference = input("\nDo you have a hospital preference? (y/n Default n): ")
    if preference == 'y':
        preference = input("Enter unique hospital name like max, fortis etc. (Don't worry about exact name): ")
        return preference
    else:
        return None


def main():
    headers = BROWSER_HEADERS[0]
    vaccines = get_vaccine_preference()
    centers = get_center_preference()

    generate_token = input("Generate New Token?, Press n if you ran the script in last 10 min (y/n Default y): ")
    generate_token = generate_token if generate_token else 'y'
    if generate_token == 'y':
        token = generate_token_otp()
        os.system("sed -i -s 's/existing_token = \".*/existing_token = \"{new_token}\"/g' {file}".format(
            new_token=token, file='./book_vaccination.py'
        ))
        os.system('rm ./book_vaccination.py-s')
    else:
        existing_token = ""
        token = existing_token
    token_generated_at = datetime.now()
    if token:
        keep_looking = True
        headers['Authorization'] = 'Bearer ' + token
        district_id = get_districts(headers)
        district_id = str(district_id[0]['district_id']) if district_id else None
        beneficiaries = get_beneficiaries(headers)
        beneficiary_ids = []
        if beneficiaries:
            for beneficiary in beneficiaries:
                beneficiary_ids.append(beneficiary['bref_id'])
        if beneficiary_ids and district_id:
            count = 0
            _start = datetime.now()
            try:
                captcha = generate_captcha(headers)
            except Exception:
                try:
                    opened = os.system('open ./captcha.png')
                    assert opened == 0
                    print("Captcha image is opened, if you can't find it. Check captcha.png in Book_Vaccine folder")
                    captcha = input("Please enter text shown in captcha: ")
                except Exception:
                    os.system('open ./')
                    print("There is some issue in your system, cannot open pop up to enter captcha")
                    captcha = input("Check captcha.png in Book_Vaccine folder, and enter the text here: ")
            while keep_looking:
                keep_looking = find_sessions(headers, district_id, vaccines, beneficiary_ids, centers, captcha)
                count = count + 1
                time.sleep(1)
                if count > 90:
                    _now = datetime.now()
                    _should_wait_for_more = 300 - (_now - _start).seconds
                    if _should_wait_for_more > 0:
                        print("To avoid blocking by server, Waiting for seconds: ", _should_wait_for_more)
                        time.sleep(_should_wait_for_more)
                    _start = datetime.now()
                    count = 0
                if (datetime.now() - token_generated_at).seconds > 600:
                    print("\n******Rerun your script as token might be expired as it is more than 10 min old*******\n")
        else:
            print("Error: Invalid Beneficiary/District")
    else:
        print("Please generate Token")


if __name__ == '__main__':
    main()
