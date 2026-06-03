"""
================================================================================
依赖注入模块（app/dependencies）
================================================================================

职责说明：
  定义 FastAPI 依赖注入函数，供 API 路由复用。

模块内容：
  - auth.py：JWT Bearer 认证依赖，提取和验证当前请求的用户

依赖注入的工作原理：
  FastAPI 的 Depends() 机制会在每次请求时调用这些函数，
  返回的值自动注入到路由处理函数的参数中。

典型使用场景：
  - 在 API 路由中保护需要登录的接口
  - 获取当前登录用户的 ID 和用户名

  @router.post("/protected")
  def protected_route(user: User = Depends(get_current_user)):
      return {"user_id": user.id, "username": user.username}

注意事项：
  - Depends(get_current_user) 抛出 HTTPException(401) 时，
    FastAPI 会自动返回 401 未授权响应
  - get_current_user_optional 用于可选认证的场景
================================================================================
"""
