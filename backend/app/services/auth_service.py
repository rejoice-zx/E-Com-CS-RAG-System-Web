"""Authentication Service - JWT Token and Password Management"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from jose import JWTError, jwt
import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.user import User


class AuthService:
    """Authentication service for JWT tokens and password management"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using bcrypt.
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password string
        """
        # Encode password to bytes, hash it, and decode back to string
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash.
        
        Args:
            plain_password: Plain text password to verify
            hashed_password: Stored password hash
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            password_bytes = plain_password.encode('utf-8')
            hashed_bytes = hashed_password.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hashed_bytes)
        except Exception:
            return False
    
    @staticmethod
    def create_access_token(
        data: dict,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create a JWT access token.
        
        Args:
            data: Payload data to encode in the token
            expires_delta: Optional custom expiration time
            
        Returns:
            Encoded JWT token string
        """
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
            )
        to_encode.update({
            "exp": expire,
            "type": "access"
        })
        return jwt.encode(
            to_encode,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )

    @staticmethod
    def create_refresh_token(
        data: dict,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create a JWT refresh token.
        
        Args:
            data: Payload data to encode in the token
            expires_delta: Optional custom expiration time
            
        Returns:
            Encoded JWT refresh token string
        """
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
            )
        to_encode.update({
            "exp": expire,
            "type": "refresh"
        })
        return jwt.encode(
            to_encode,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )
    
    @staticmethod
    def create_tokens(user_id: int, username: str) -> Tuple[str, str, int]:
        """
        Create both access and refresh tokens for a user.
        
        Args:
            user_id: User's database ID
            username: User's username
            
        Returns:
            Tuple of (access_token, refresh_token, expires_in_seconds)
        """
        token_data = {"sub": str(user_id), "username": username}
        access_token = AuthService.create_access_token(token_data)
        refresh_token = AuthService.create_refresh_token(token_data)
        expires_in = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return access_token, refresh_token, expires_in
    
    @staticmethod
    def verify_token(token: str, token_type: str = "access") -> Optional[dict]:
        """
        Verify and decode a JWT token.
        
        Args:
            token: JWT token string to verify
            token_type: Expected token type ("access" or "refresh")
            
        Returns:
            Decoded token payload if valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            # Verify token type
            if payload.get("type") != token_type:
                return None
            return payload
        except JWTError:
            return None
    
    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        username: str,
        password: str
    ) -> Optional[User]:
        """
        Authenticate a user by username and password.
        
        Args:
            db: Database session
            username: User's username
            password: User's plain text password
            
        Returns:
            User object if authentication successful, None otherwise
        """
        result = await db.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        if not AuthService.verify_password(password, user.password_hash):
            return None
        if not user.is_active:
            return None
        
        return user
    
    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """
        Get a user by their ID.
        
        Args:
            db: Database session
            user_id: User's database ID
            
        Returns:
            User object if found, None otherwise
        """
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_by_username(
        db: AsyncSession,
        username: str
    ) -> Optional[User]:
        """
        Get a user by their username.
        
        Args:
            db: Database session
            username: User's username
            
        Returns:
            User object if found, None otherwise
        """
        result = await db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_user(
        db: AsyncSession,
        username: str,
        password: str,
        display_name: str,
        email: Optional[str] = None,
        role: str = "cs",
        is_active: bool = False
    ) -> User:
        """
        Create a new user.
        
        Args:
            db: Database session
            username: User's username
            password: User's plain text password (will be hashed)
            display_name: User's display name
            email: Optional email address
            role: User role (default: "cs")
            is_active: Whether user is active (default: False for pending approval)
            
        Returns:
            Created User object
        """
        user = User(
            username=username,
            password_hash=AuthService.hash_password(password),
            display_name=display_name,
            email=email,
            role=role,
            is_active=is_active
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
    
    @staticmethod
    async def update_last_login(db: AsyncSession, user: User) -> None:
        """
        Update user's last login timestamp.
        
        Args:
            db: Database session
            user: User object to update
        """
        user.last_login = datetime.now(timezone.utc)
        await db.commit()


# Convenience functions for direct import
hash_password = AuthService.hash_password
verify_password = AuthService.verify_password
create_access_token = AuthService.create_access_token
create_refresh_token = AuthService.create_refresh_token
create_tokens = AuthService.create_tokens
verify_token = AuthService.verify_token
