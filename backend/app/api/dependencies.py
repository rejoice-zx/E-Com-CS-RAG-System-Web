"""API Dependencies - Authentication and Authorization"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.database import get_db
from app.services.auth_service import AuthService
from app.models.user import User


# HTTP Bearer token security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.
    
    Args:
        credentials: Bearer token from Authorization header
        db: Database session
        
    Returns:
        Authenticated User object
        
    Raises:
        HTTPException: 401 if token is invalid or user not found
    """
    token = credentials.credentials
    
    # Verify access token
    payload = AuthService.verify_token(token, token_type="access")
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Guest tokens cannot access staff-only endpoints
    if payload.get("role") == "guest":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="访客令牌无法访问此接口",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from database
    try:
        user_id = int(payload.get("sub"))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await AuthService.get_user_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户已被禁用",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Optional authentication - returns User if token is valid, None otherwise.
    Used for endpoints accessible by both anonymous and authenticated users.
    Guest tokens return None (no DB user).
    """
    if not credentials:
        return None

    token = credentials.credentials
    payload = AuthService.verify_token(token, token_type="access")

    if not payload:
        return None

    # Guest tokens have role=guest, no DB user
    if payload.get("role") == "guest":
        return None

    try:
        user_id = int(payload.get("sub"))
        user = await AuthService.get_user_by_id(db, user_id)
        if user and user.is_active:
            return user
    except (ValueError, TypeError):
        pass

    return None


def get_customer_id_from_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> Optional[str]:
    """
    Extract customer_id from JWT token.
    For guest tokens: returns visitor_xxx
    For staff tokens: returns user_xxx
    Returns None if no valid token.
    """
    if not credentials:
        return None

    payload = AuthService.verify_token(credentials.credentials, token_type="access")
    if not payload:
        return None

    sub = payload.get("sub", "")
    role = payload.get("role", "")

    if role == "guest":
        return sub  # already visitor_xxx
    else:
        return f"user_{sub}"


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to ensure user is active.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Active User object
        
    Raises:
        HTTPException: 401 if user is not active
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户已被禁用"
        )
    return current_user



# Role-based permission mapping
# Maps roles to allowed API endpoint prefixes/patterns
ROLE_PERMISSIONS = {
    "admin": [
        "/api/auth",
        "/api/chat",
        "/api/knowledge",
        "/api/products",
        "/api/human",
        "/api/statistics",
        "/api/performance",
        "/api/logs",
        "/api/settings",
        "/api/users",
    ],
    "cs": [
        "/api/auth",
        "/api/chat",
        "/api/products",
        "/api/human",
    ],
}


def require_roles(allowed_roles: List[str]):
    """
    Dependency factory to require specific roles for an endpoint.
    
    Args:
        allowed_roles: List of role names that can access the endpoint
        
    Returns:
        Dependency function that validates user role
        
    Example:
        @router.get("/admin-only")
        async def admin_endpoint(user: User = Depends(require_roles(["admin"]))):
            ...
    """
    async def role_checker(
        current_user: User = Depends(get_current_user)
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足"
            )
        return current_user
    
    return role_checker


def require_admin():
    """
    Dependency to require admin role.
    
    Returns:
        Dependency function that validates admin role
    """
    return require_roles(["admin"])


def require_cs_or_admin():
    """
    Dependency to require cs or admin role.
    
    Returns:
        Dependency function that validates cs or admin role
    """
    return require_roles(["admin", "cs"])


class RBACChecker:
    """
    RBAC permission checker class for more complex permission scenarios.
    Can be used as a dependency or called directly.
    """
    
    def __init__(self, allowed_roles: List[str]):
        """
        Initialize RBAC checker with allowed roles.
        
        Args:
            allowed_roles: List of role names that can access the resource
        """
        self.allowed_roles = allowed_roles
    
    async def __call__(
        self,
        current_user: User = Depends(get_current_user)
    ) -> User:
        """
        Check if current user has required role.
        
        Args:
            current_user: Current authenticated user
            
        Returns:
            User if authorized
            
        Raises:
            HTTPException: 403 if user lacks required role
        """
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足"
            )
        return current_user
    
    @staticmethod
    def check_permission(user_role: str, endpoint: str) -> bool:
        """
        Check if a role has permission to access an endpoint.
        
        Args:
            user_role: User's role
            endpoint: API endpoint path
            
        Returns:
            True if role has permission, False otherwise
        """
        allowed_endpoints = ROLE_PERMISSIONS.get(user_role, [])
        return any(endpoint.startswith(prefix) for prefix in allowed_endpoints)
    
    @staticmethod
    def get_allowed_endpoints(user_role: str) -> List[str]:
        """
        Get list of allowed endpoint prefixes for a role.
        
        Args:
            user_role: User's role
            
        Returns:
            List of allowed endpoint prefixes
        """
        return ROLE_PERMISSIONS.get(user_role, [])


# Convenience instances for common role checks
AdminRequired = RBACChecker(["admin"])
CSOrAdminRequired = RBACChecker(["admin", "cs"])
