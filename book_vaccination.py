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
import re
from hashlib import sha256

API_DISTRICT = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByDistrict"
API_PINCODE = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByPin"
API_BOOK = "https://cdn-api.co-vin.in/api/v2/appointment/schedule"
CAPTCHA_URL = "https://cdn-api.co-vin.in/api/v2/auth/getRecaptcha"

DISTRICT = 'district_id'
DATE = 'date'

BROWSER_HEADERS = [{'user-agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.76 Safari/537.36'},
                   {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'}]


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


def find_sessions(headers, district_id, pincode, vaccine_preference, beneficiary_ids, center_preference, captcha, dose):
    url = get_url_with_query_params(district_id, pincode)
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
                preferred_dose = 'available_capacity_dose' + dose
                if session['min_age_limit'] == 18 and session['available_capacity'] >= doses and session[preferred_dose] >= doses:
                    print('******', center['name'], session['date'], session['vaccine'], session['available_capacity'], session[preferred_dose])
                    found = True
                    os.system('echo -e "\a"')
                    if (not vaccine_preference or session['vaccine'] == vaccine_preference) and (not center_preference or center_preference.lower() in center['name'].lower()):
                        data = {'center_id': center['center_id'], 'session_id': session['session_id'],
                                'beneficiaries': beneficiary_ids, 'slot': session['slots'][-1], 'captcha': 'nMReQ',
                                'dose': int(dose)}
                        data['captcha'] = captcha
                        book_response = requests.post(API_BOOK, data=json.dumps(data), headers=headers)
                        print(book_response.status_code)
                        print(book_response.text)
                        if book_response.status_code in [200, 201]:
                            print('Thanks to Pulkit, your appointment is booked.')
                            booked = True
                            return not booked
        print('******No slot available in centers: ', len(centers)) if not found else None
    else:
        print('******Error: ', response.status_code)
        print('******Error: ', response.text)
    return not booked


def captcha_builder(resp):
    with open('captcha.svg', 'w') as f:
        f.write(re.sub('(<path d=)(.*?)(fill=\"none\"/>)', '', resp['captcha']))

    drawing = svg2rlg('captcha.svg')
    renderPM.drawToFile(drawing, "captcha.png", fmt="PNG")

    import PySimpleGUI
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


def get_url_with_query_params(district_id, pincode):
    if district_id:
        params = {DISTRICT: district_id, DATE: datetime.now().date().strftime("%d-%m-%Y")}
        query_params_url = ''
        for param in params:
            query_params_url = query_params_url + param + '=' + params[param] + '&'
        if query_params_url:
            query_params_url = '?' + query_params_url[:-1]
        url = API_DISTRICT + query_params_url
        return url
    elif pincode:
        params = {'pincode': pincode, DATE: datetime.now().date().strftime("%d-%m-%Y")}
        query_params_url = ''
        for param in params:
            query_params_url = query_params_url + param + '=' + params[param] + '&'
        if query_params_url:
            query_params_url = '?' + query_params_url[:-1]
        url = API_PINCODE + query_params_url
        return url
    print('Something went wrong')
    sys.exit()


def get_headers():
    headers = BROWSER_HEADERS[1]
    headers['origin'] = 'https://selfregistration.cowin.gov.in'
    headers['referer'] = 'https://selfregistration.cowin.gov.in/'
    headers['content-type'] = 'application/json'
    return headers


def generate_token_otp():
    """
    This function generate OTP and returns a new token
    """
    mobile = input("Enter the registered mobile number: ")
    headers = get_headers()

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
    headers = get_headers()
    vaccines = get_vaccine_preference()
    dose = input("\nEnter 1 for 1st dose, 2 for 2nd dose? (Default 1): ")
    dose = '2' if dose == '2' else '1'
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
        district_or_pin = input("Search centers by district name or pincode?, Enter 0 for district, 1 for pincode, Default 0: ")
        district_or_pin = int(district_or_pin) if district_or_pin and int(district_or_pin) in [0, 1] else 0
        pincodes = []
        district_id = None
        if district_or_pin == 1:
            number_of_pincodes = input("How many pincodes do you want to enter?: Default 1: ")
            number_of_pincodes = int(number_of_pincodes) if number_of_pincodes and int(number_of_pincodes) > 0 else 1
            for index in range(0, number_of_pincodes):
                print('Pincode Number ', index + 1)
                pincode = input("Enter valid pincode: ")
                if len(pincode) != 6:
                    print("Invalid pincode")
                    print('Pincode Number ', index + 1)
                    pincode = input("Enter valid pincode: ")
                if len(pincode) != 6:
                    print("Invalid pincode, ignoring this")
                else:
                    pincodes.append(pincode)
                print("\n\n")
            if not pincodes:
                print("You are not entering valid pincodes, Please search by district")
        if district_or_pin != 1 or not pincodes:
            district_id = get_districts(headers)
            district_id = str(district_id[0]['district_id']) if district_id else None
        beneficiaries = get_beneficiaries(headers)
        beneficiary_ids = []
        if beneficiaries:
            for beneficiary in beneficiaries:
                beneficiary_ids.append(beneficiary['bref_id'])
        if beneficiary_ids and (district_id or pincodes):
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
                if pincodes:
                    for pincode in pincodes:
                        keep_looking = find_sessions(headers, district_id, pincode, vaccines, beneficiary_ids, centers, captcha, dose)
                        if not keep_looking:
                            break
                        count = count + 1
                        time.sleep(2)
                else:
                    keep_looking = find_sessions(headers, district_id, None, vaccines, beneficiary_ids, centers, captcha, dose)
                    count = count + 1
                    time.sleep(2)
                if count > 20:
                    _now = datetime.now()
                    _should_wait_for_more = 60 - (_now - _start).seconds
                    if _should_wait_for_more > 0:
                        print("To avoid blocking by server, Waiting for seconds: ", _should_wait_for_more)
                        time.sleep(_should_wait_for_more)
                    _start = datetime.now()
                    count = 0
                if (datetime.now() - token_generated_at).seconds > 600:
                    print("\n******Rerun your script as token might be expired as it is more than 10 min old*******\n")
        else:
            print("Error: Invalid Beneficiary/District/Pincode")
    else:
        print("Please generate Token by otp")


if __name__ == '__main__':
    main()
