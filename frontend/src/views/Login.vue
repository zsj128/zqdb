<template>
  <div class="login-page">
    <div class="login-box">
      <h2>用户登录</h2>
      <form @submit.prevent="handleLogin">
        <div class="form-group">
          <label>用户名</label>
          <input v-model="username" type="text" placeholder="请输入用户名" />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input v-model="password" type="password" placeholder="请输入密码" />
        </div>
        <button type="submit" class="btn-login">登 录</button>
      </form>
      <p class="tip">{{ message }}</p>
      <p class="link-to-register">还没有账号？<a href="#" @click.prevent="$emit('switch', 'register')">去注册</a></p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(['switch', 'login-success'])

const username = ref('')
const password = ref('')
const message = ref('')

async function handleLogin() {
  if (!username.value || !password.value) {
    message.value = '请填写完整信息'
    return
  }
  try {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value, password: password.value })
    })
    const data = await res.json()
    if (res.ok) {
      // 保存token到localStorage
      localStorage.setItem('token', data.token)
      localStorage.setItem('username', data.username)
      localStorage.setItem('user_id', data.user_id)
      localStorage.setItem('is_admin', data.is_admin ? '1' : '0')
      emit('login-success', { username: data.username, userId: data.user_id, isAdmin: !!data.is_admin })
    } else {
      message.value = data.detail || '登录失败'
    }
  } catch (e) {
    message.value = '网络错误，请稍后重试'
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 60vh;
}
.login-box {
  width: 360px;
  padding: 36px 32px;
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 20px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.25);
}
.login-box h2 {
  text-align: center;
  margin-bottom: 28px;
  font-size: 1.5em;
  font-weight: 700;
  background: linear-gradient(135deg, #fff, #a5b4fc);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.form-group {
  margin-bottom: 18px;
}
.form-group label {
  display: block;
  font-size: 0.9em;
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 8px;
  font-weight: 500;
}
.form-group input {
  width: 100%;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  font-size: 0.95em;
  outline: none;
  transition: all 0.3s ease;
  box-sizing: border-box;
  color: rgba(255, 255, 255, 0.9);
}
.form-group input::placeholder { color: rgba(255, 255, 255, 0.3); }
.form-group input:focus {
  border-color: rgba(102, 126, 234, 0.6);
  box-shadow: 0 0 16px rgba(102, 126, 234, 0.15);
  background: rgba(255, 255, 255, 0.09);
}
.btn-login {
  width: 100%;
  padding: 13px;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: #fff;
  border: none;
  border-radius: 12px;
  font-size: 1em;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  margin-top: 6px;
  letter-spacing: 2px;
}
.btn-login:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
}
.tip {
  text-align: center;
  color: #fca5a5;
  font-size: 0.88em;
  margin-top: 16px;
}
.link-to-register {
  text-align: center;
  font-size: 0.9em;
  color: rgba(255, 255, 255, 0.45);
  margin-top: 18px;
}
.link-to-register a {
  color: #a5b4fc;
  text-decoration: none;
  font-weight: 500;
  transition: all 0.3s;
}
.link-to-register a:hover {
  color: #c4b5fd;
  text-shadow: 0 0 12px rgba(165, 180, 252, 0.4);
}
</style>
