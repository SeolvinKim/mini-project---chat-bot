from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
'''
/login/

userid='user'   -> 틀리면 로그인 실패
password='1234' -> 틀리면 비밀번호가 다릅니다
둘 다 맞으면 로그인 성공
'''

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # React 개발 서버만 허용(허용할 출처)
    allow_credentials=True,  #(인증정보 허용, 쿠키, jWT토큰 등등)
    allow_methods=["*"],     #허용할 HTTP메서드(get, post, patch, put, delete)
    allow_headers=["*"],     #허용할 http헤더(Content-Type, Authorization)
)

class Login(BaseModel):
    userid : str
    password : str

USERID ='user'
PASSWORD = '1234'

@app.post('/login/')
async def login(login:Login):
    if login.userid != USERID:
        return {'로그인 실패'}
    
    if login.password != PASSWORD:
        return {'비밀번호가 다릅니다'}

    return {'로그인 성공'}
