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
      emit('login-success', { username: data.username, userId: data.user_id })
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
  width: 340px;
  padding: 32px;
  border: 1px solid #e8e8e8;
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}
.login-box h2 {
  text-align: center;
  margin-bottom: 24px;
  font-size: 1.4em;
  color: #1a56db;
}
.form-group {
  margin-bottom: 16px;
}
.form-group label {
  display: block;
  font-size: 0.9em;
  color: #555;
  margin-bottom: 6px;
}
.form-group input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 0.95em;
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
}
.form-group input:focus {
  border-color: #1a56db;
}
.btn-login {
  width: 100%;
  padding: 11px;
  background: #1a56db;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 1em;
  cursor: pointer;
  transition: background 0.2s;
  margin-top: 4px;
}
.btn-login:hover {
  background: #1645b3;
}
.tip {
  text-align: center;
  color: #e74c3c;
  font-size: 0.88em;
  margin-top: 14px;
}
.link-to-register {
  text-align: center;
  font-size: 0.9em;
  color: #666;
  margin-top: 16px;
}
.link-to-register a {
  color: #1a56db;
  text-decoration: none;
}
.link-to-register a:hover {
  text-decoration: underline;
}
</style>
