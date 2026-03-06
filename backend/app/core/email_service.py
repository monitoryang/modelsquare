"""Email service for sending verification codes"""

import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import redis.asyncio as redis

from app.core.config import settings
from app.core.redis import get_redis


class EmailService:
    """Email service for verification codes"""

    VERIFICATION_CODE_KEY_PREFIX = "email_verification:"
    CODE_LENGTH = 6
    
    @staticmethod
    def generate_code() -> str:
        """Generate a random 6-digit verification code"""
        return ''.join(random.choices(string.digits, k=EmailService.CODE_LENGTH))
    
    @staticmethod
    def _get_redis_key(email: str) -> str:
        """Get Redis key for email verification code"""
        return f"{EmailService.VERIFICATION_CODE_KEY_PREFIX}{email}"
    
    @staticmethod
    async def send_verification_code(email: str) -> tuple[bool, str]:
        """
        Send verification code to email address
        Returns: (success, message)
        """
        # Check if SMTP is configured
        if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
            # Development mode: return code directly without sending email
            code = EmailService.generate_code()
            redis_client = await get_redis()
            key = EmailService._get_redis_key(email)
            # Store code in Redis with expiration
            await redis_client.setex(
                key,
                settings.EMAIL_CODE_EXPIRE_MINUTES * 60,
                code
            )
            return True, f"[DEV MODE] 验证码: {code}"
        
        # Generate verification code
        code = EmailService.generate_code()
        
        # Store code in Redis
        redis_client = await get_redis()
        key = EmailService._get_redis_key(email)
        
        # Check rate limit: only allow 1 code per minute
        ttl = await redis_client.ttl(key)
        if ttl > (settings.EMAIL_CODE_EXPIRE_MINUTES - 1) * 60:
            return False, "请求过于频繁，请稍后再试"
        
        # Store new code
        await redis_client.setex(
            key,
            settings.EMAIL_CODE_EXPIRE_MINUTES * 60,
            code
        )
        
        # Send email
        try:
            msg = MIMEMultipart()
            msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            msg['To'] = email
            msg['Subject'] = f"【{settings.APP_NAME}】邮箱验证码"
            
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background: #f9f9f9; padding: 30px; border-radius: 10px;">
                    <h2 style="color: #333; margin-bottom: 20px;">邮箱验证码</h2>
                    <p style="color: #666;">您好，</p>
                    <p style="color: #666;">您的验证码是：</p>
                    <div style="background: #667eea; color: white; font-size: 32px; text-align: center; 
                                padding: 20px; border-radius: 8px; letter-spacing: 8px; margin: 20px 0;">
                        {code}
                    </div>
                    <p style="color: #666;">验证码有效期为 {settings.EMAIL_CODE_EXPIRE_MINUTES} 分钟，请尽快使用。</p>
                    <p style="color: #999; font-size: 12px; margin-top: 30px;">
                        如果您没有请求此验证码，请忽略此邮件。
                    </p>
                    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                    <p style="color: #999; font-size: 12px;">
                        此邮件由 {settings.APP_NAME} 系统自动发送，请勿回复。
                    </p>
                </div>
            </body>
            </html>
            """
            msg.attach(MIMEText(body, 'html', 'utf-8'))
            
            # Connect to SMTP server and send
            if settings.SMTP_USE_TLS:
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
            
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()
            
            return True, "验证码已发送，请检查您的邮箱"
            
        except Exception as e:
            # Delete the stored code on failure
            await redis_client.delete(key)
            return False, f"邮件发送失败: {str(e)}"
    
    @staticmethod
    async def verify_code(email: str, code: str) -> tuple[bool, str]:
        """
        Verify the email verification code
        Returns: (success, message)
        """
        redis_client = await get_redis()
        key = EmailService._get_redis_key(email)
        
        stored_code = await redis_client.get(key)
        
        if not stored_code:
            return False, "验证码已过期或不存在，请重新获取"
        
        if stored_code != code:
            return False, "验证码错误"
        
        # Delete the code after successful verification
        await redis_client.delete(key)
        return True, "验证码正确"
    
    @staticmethod
    def is_jouav_email(email: str) -> bool:
        """Check if email is a jouav.com domain email"""
        if not email:
            return False
        domain = email.split('@')[-1].lower()
        return domain == settings.SUPERUSER_EMAIL_DOMAIN.lower()


email_service = EmailService()
