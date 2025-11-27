from flask_mail import Message

# ลบ send_line_notify และ import requests ออกแล้ว

def send_email(to_email, subject, body):
    # import ใน function เพื่อเลี่ยง circular import กับ app.py
    from app import mail
    
    msg = Message(subject, recipients=[to_email])
    msg.body = body
    try:
        mail.send(msg)
        print(f"Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def send_notification(to_email, message, subject='Task Notification'):
    # เรียกใช้ส่งเมลทันที ไม่ต้องเช็ค Line
    send_email(to_email, subject, message)