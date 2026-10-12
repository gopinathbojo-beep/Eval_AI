import urllib.request
import json

req = urllib.request.Request(
    'http://127.0.0.1:8000/api/auth/login',
    data=json.dumps({'email': 'you@school.org', 'password': 'pass1234'}).encode(),
    headers={'Content-Type': 'application/json'}
)
res = urllib.request.urlopen(req)
token = json.loads(res.read())['access_token']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# 1. Get classes and subjects
req_c = urllib.request.Request('http://127.0.0.1:8000/api/classes', headers=headers)
classes = json.loads(urllib.request.urlopen(req_c).read())
req_s = urllib.request.Request('http://127.0.0.1:8000/api/subjects', headers=headers)
subjects = json.loads(urllib.request.urlopen(req_s).read())

# 2. Create exam without academic_year
create_payload = {
    'name': 'Live Verification Exam',
    'class_id': classes[0]['id'],
    'subject_id': subjects[0]['id'],
    'exam_type': 'Test',
    'total_marks': 50
}
req_create = urllib.request.Request(
    'http://127.0.0.1:8000/api/exams',
    data=json.dumps(create_payload).encode(),
    headers=headers
)
exam = json.loads(urllib.request.urlopen(req_create).read())
print(f"Exam created successfully: {exam['id']}")
print(f"Auto academic year: {exam['academic_year']}")

# 3. Check answer keys endpoint
eid = exam['id']
req_keys = urllib.request.Request(f"http://127.0.0.1:8000/api/exams/{eid}/answer-keys", headers=headers)
keys = json.loads(urllib.request.urlopen(req_keys).read())
print(f"Answer keys response: keys count={len(keys['keys'])}, locked={keys['locked']}")
