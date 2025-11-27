import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or '0d2794d647be25596f5de435e303a8b29aff0f9293e39ecf05eba110d485a373'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Email Config
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'anapat2014seen@gmail.com'
    MAIL_PASSWORD = 'wmmp kxmr aryl klnx'
    MAIL_DEFAULT_SENDER = 'anapat2014seen@gmail.com'
    
    # Redis Config (ปิดไว้ก่อน)
    # REDIS_URI = 'redis://default:...'
    
    # ใช้ memory:// เพื่อความลื่นไหลในการรันเทส
    LIMITER_STORAGE_URI = "memory://"