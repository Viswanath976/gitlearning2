import boto3
import pandas as pd
import json
import os
import uuid
from datetime import datetime
from io import StringIO

from cleaner import clean_dataframe
from snowflake_conn import (
    get_snowflake_conn,
    is_suppressed,
    get_reoon_cache,
    get_eo_cache,
    save_reoon,
    save_eo
)
from reoon_api import verify_reoon
from eo_api import verify_eo

S3 = boto3.client('s3')
BUCKET = os.environ['S3_BUCKET']

def check_lead(conn, email):
    # Step 1: Suppression
    if is_suppressed(conn, email):
        return 'SUPPRESSED', None, None
    # Step 2: Reoon
    cache = get_reoon_cache(
        conn, email)
    if cache:
        reoon_safe = cache[0]
        reoon_status = cache[1]
    else:
        result = verify_reoon(email)
        if not result:
            return 'REOON_ERROR',\
                None, None
        save_reoon(conn, email, result)
        reoon_safe = result.get(
            'is_safe_to_send', False)
        reoon_status = result.get(
            'status','')
    if not reoon_safe:
        return 'REOON_FAILED',\
            reoon_status, None
    # Step 3: EO
    cache = get_eo_cache(conn, email)
    if cache:
        eo_safe = cache[0]
        eo_status = cache[1]
    else:
        result = verify_eo(email)
        if not result:
            return 'EO_ERROR',\
                reoon_status, None
        save_eo(conn, email, result)
        unsafe = ['Complainer',
            'Undeliverable',
            'Disabled','Unknown']
        eo_safe = result.get(
            'Result','') not in unsafe
        eo_status = result.get(
            'Result','')
    if not eo_safe:
        return 'EO_FAILED',\
            reoon_status, eo_status
    return 'PASSED',\
        reoon_status, eo_status

def lambda_handler(event, context):
    input_key = event.get(
        'input_key',
        'input/MortgageList.csv')
    run_id = event.get('run_id',
        f"RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
        f"{uuid.uuid4().hex[:8]}")

    print(f"Input: {input_key}")
    print(f"Run ID: {run_id}")

    # Read CSV from S3
    obj = S3.get_object(
        Bucket=BUCKET, Key=input_key)
    df = pd.read_csv(StringIO(
        obj['Body'].read()
        .decode('latin-1')))
    print(f"Rows: {len(df)}")

    # Clean
    df = clean_dataframe(df)

    # Snowflake connection
    conn = get_snowflake_conn()

    results = []
    passed=failed=suppressed=errors=0

    for idx, row in df.iterrows():
        email = row.get('email')
        if not email:
            continue

        status, reoon, eo = \
            check_lead(conn, email)

        r = row.to_dict()
        r['HYGIENE_STATUS'] = status
        r['REOON_RESULT'] = reoon
        r['EO_RESULT'] = eo
        r['RUN_ID'] = run_id
        r['PROCESSED_AT'] = \
            datetime.now().isoformat()
        results.append(r)

        if status == 'PASSED':
            passed += 1
        elif status == 'SUPPRESSED':
            suppressed += 1
        elif 'ERROR' in status:
            errors += 1
        else:
            failed += 1

        print(f"{idx+1}: {email} = {status}")

    conn.close()

    # Save output CSV to S3
    out_df = pd.DataFrame(results)
    out_key = (f"stage1_hygiene/"
        f"mortgage_hygiene_{run_id}.csv")
    buf = StringIO()
    out_df.to_csv(buf, index=False)
    S3.put_object(
        Bucket=BUCKET,
        Key=out_key,
        Body=buf.getvalue())

    summary = {
        'run_id': run_id,
        'total': len(df),
        'passed': passed,
        'failed': failed,
        'suppressed': suppressed,
        'errors': errors,
        'output_file': out_key
    }
    print(f"Done! {json.dumps(summary)}")
    return summary
