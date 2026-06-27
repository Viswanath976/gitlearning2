import re
import pandas as pd

def clean_email(val):
    if pd.isna(val):
        return None
    return str(val).lower().strip()

def clean_phone(val):
    if pd.isna(val):
        return None
    d = re.sub(r'\D','',str(val))
    if len(d)==11 and d[0]=='1':
        d = d[1:]
    return d if len(d)==10 else None

def clean_money(val):
    if pd.isna(val):
        return None
    val = str(val).replace(
        '$','').replace(',','')
    nums = re.findall(
        r'\d+(?:\.\d+)?', val)
    if not nums:
        return None
    return int(float(
        max(nums, key=float)))

def clean_credit(val):
    if pd.isna(val):
        return None
    mapping = {
        'excellent':'Excellent',
        'good':'Good',
        'fair':'Fair',
        'poor':'Poor',
        'somecreditproblems':'Fair',
        'some credit problems':'Fair',
    }
    return mapping.get(
        str(val).lower().strip(),
        str(val).strip())

def clean_zip(val):
    if pd.isna(val):
        return None
    return str(val).zfill(5)[:5]

def clean_dataframe(df):
    col_map = {
        'Last Name':'last_name',
        'First Name':'first_name',
        'Email':'email',
        'Home Phone':'phone',
        'Mobile Phone':'mobile_phone',
        'Mailing Address':'address',
        'Mailing City':'city',
        'Mailing State':'state',
        'Mailing Zip':'zip',
        'Loan Purpose':'loan_type',
        'Loan Amount':'loan_amount',
        'Credit Rating':'credit_band',
        'Current Balance':
            'mortgage_balance',
        'First Mortgage Amount':
            'first_mortgage_amount',
        'IsMilitary':'is_military',
        'TrustedFormID':
            'trusted_form_url',
    }
    df = df.rename(columns=col_map)
    required = [
        'email','first_name',
        'last_name','phone',
        'mobile_phone','address',
        'city','state','zip',
        'loan_type','loan_amount',
        'credit_band',
        'mortgage_balance',
        'first_mortgage_amount',
        'is_military',
        'trusted_form_url'
    ]
    for col in required:
        if col not in df.columns:
            df[col] = None
    df['email'] = df['email']\
        .apply(clean_email)
    df['phone'] = df['phone']\
        .apply(clean_phone)
    df['mobile_phone'] = \
        df['mobile_phone']\
        .apply(clean_phone)
    df['zip'] = df['zip']\
        .apply(clean_zip)
    df['state'] = df['state']\
        .str.upper().str.strip()
    df['first_name'] = \
        df['first_name'].str.strip()
    df['last_name'] = \
        df['last_name'].str.strip()
    df['credit_band'] = \
        df['credit_band']\
        .apply(clean_credit)
    df['loan_amount'] = \
        df['loan_amount']\
        .apply(clean_money)
    df['mortgage_balance'] = \
        df['mortgage_balance']\
        .apply(clean_money)
    return df
