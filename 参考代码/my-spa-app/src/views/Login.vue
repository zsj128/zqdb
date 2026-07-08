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
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const username = ref('')
const password = ref('')
const message = ref('')

function handleLogin() {
  if (!username.value || !password.value) {
    message.value = '请填写完整信息'
    return
  }
  if (username.value === 'admin' && password.value === '123456') {
    message.value = ''
    router.push({ name: 'home' })
  } else {
    message.value = '用户名或密码错误'
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
  border-color: #42b883;
}
.btn-login {
  width: 100%;
  padding: 11px;
  background: #42b883;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 1em;
  cursor: pointer;
  transition: background 0.2s;
  margin-top: 4px;
}
.btn-login:hover {
  background: #369e6d;
}
.tip {
  text-align: center;
  color: #e74c3c;
  font-size: 0.88em;
  margin-top: 14px;
}
</style>
