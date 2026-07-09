<template>
  <div class="register-page">
    <div class="register-box">
      <h2>用户注册</h2>
      <form @submit.prevent="handleRegister">
        <!-- 用户名 -->
        <div class="form-group">
          <label>用户名</label>
          <input v-model="username" type="text" placeholder="4-16位，字母开头"
            :class="{ 'error-border': usernameTouched && !usernameValid, 'success-border': usernameTouched && usernameValid }"
            @blur="usernameTouched = true" />
          <div class="tip" :class="usernameTouched ? (usernameValid ? 'success' : 'error') : ''">
            {{ usernameMessage }}
          </div>
        </div>

        <!-- 密码 -->
        <div class="form-group">
          <label>密码</label>
          <div class="pwd-wrapper">
            <input v-model="password" :type="showPassword ? 'text' : 'password'"
              placeholder="至少8位，包含数字和字母和特殊字符"
              :class="{ 'error-border': passwordTouched && !passwordValid, 'success-border': passwordTouched && passwordValid }"
              @blur="passwordTouched = true" />
            <span class="toggle-pwd" @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示' }}</span>
          </div>
          <div class="password-bar"><div class="password-bar-fill" :class="passwordStrengthClass"></div></div>
          <div class="tip" :class="passwordTouched ? (passwordValid ? 'success' : 'error') : ''">
            {{ passwordMessage }}
          </div>
        </div>

        <!-- 确认密码 -->
        <div class="form-group">
          <label>确认密码</label>
          <div class="pwd-wrapper">
            <input v-model="password2" :type="showPassword2 ? 'text' : 'password'"
              placeholder="再次输入密码"
              :class="{ 'error-border': password2Touched && !password2Valid, 'success-border': password2Touched && password2Valid }"
              @blur="password2Touched = true" />
            <span class="toggle-pwd" @click="showPassword2 = !showPassword2">{{ showPassword2 ? '隐藏' : '显示' }}</span>
          </div>
          <div class="tip" :class="password2Touched ? (password2Valid ? 'success' : 'error') : ''">
            {{ password2Message }}
          </div>
        </div>

        <!-- 邮箱 -->
        <div class="form-group">
          <label>邮箱</label>
          <input v-model="email" type="email" placeholder="请输入邮箱"
            :class="{ 'error-border': emailTouched && !emailValid, 'success-border': emailTouched && emailValid }"
            @blur="emailTouched = true" />
          <div class="tip" :class="emailTouched ? (emailValid ? 'success' : 'error') : ''">
            {{ emailMessage }}
          </div>
        </div>

        <!-- 手机号 -->
        <div class="form-group">
          <label>手机号</label>
          <input v-model="phone" type="tel" placeholder="11位国内手机号"
            :class="{ 'error-border': phoneTouched && !phoneValid, 'success-border': phoneTouched && phoneValid }"
            @blur="phoneTouched = true" />
          <div class="tip" :class="phoneTouched ? (phoneValid ? 'success' : 'error') : ''">
            {{ phoneMessage }}
          </div>
        </div>

        <button type="submit" class="btn-register" :disabled="!allValid">注 册</button>
      </form>
      <p class="tip error" style="text-align:center; margin-top:12px;">{{ message }}</p>
      <p class="link-to-login">已有账号？<a href="#" @click.prevent="$emit('switch', 'login')">去登录</a></p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const emit = defineEmits(['switch', 'register-success'])

// 表单数据
const username = ref('')
const password = ref('')
const password2 = ref('')
const email = ref('')
const phone = ref('')
const message = ref('')

// 控制密码显示
const showPassword = ref(false)
const showPassword2 = ref(false)

// 是否已触碰（用于显示验证状态）
const usernameTouched = ref(false)
const passwordTouched = ref(false)
const password2Touched = ref(false)
const emailTouched = ref(false)
const phoneTouched = ref(false)

// 用户名验证
const usernameValid = computed(() => {
  if (!username.value) return false
  return /^[a-zA-Z][a-zA-Z0-9_]{3,15}$/.test(username.value)
})
const usernameMessage = computed(() => {
  if (!usernameTouched.value) return ''
  if (!username.value) return '用户名不能为空'
  if (!usernameValid.value) return '4-16位，字母开头，仅字母数字下划线'
  return '用户名格式正确'
})

// 密码验证
const passwordValid = computed(() => {
  if (!password.value) return false
  if (password.value.length < 8) return false
  return /^(?=.*[0-9])(?=.*[a-zA-Z])(?=.*[!@#$%^&*])[a-zA-Z0-9!@#$%^&*]+$/.test(password.value)
})
const passwordMessage = computed(() => {
  if (!passwordTouched.value) return ''
  if (!password.value) return '密码不能为空'
  if (password.value.length < 8) return '密码长度不能小于8位'
  if (!passwordValid.value) return '密码必须包含数字、字母和特殊字符'
  return '密码格式正确'
})

// 密码强度
const passwordStrengthLevel = computed(() => {
  let level = 0
  if (/[a-z]/.test(password.value)) level++
  if (/[A-Z]/.test(password.value)) level++
  if (/[0-9]/.test(password.value)) level++
  if (/[!@#$%^&*]/.test(password.value)) level++
  if (password.value.length >= 8) level++
  return level
})
const passwordStrengthClass = computed(() => {
  if (!password.value) return ''
  const l = passwordStrengthLevel.value
  if (l <= 2) return 'strength-weak'
  if (l <= 4) return 'strength-medium'
  return 'strength-strong'
})

// 确认密码验证
const password2Valid = computed(() => {
  return password2.value === password.value && password2.value !== ''
})
const password2Message = computed(() => {
  if (!password2Touched.value) return ''
  if (password2Valid.value) return '密码一致'
  return '密码不一致'
})

// 邮箱验证（必填）
const emailValid = computed(() => {
  if (!email.value) return false
  return /^[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+$/.test(email.value)
})
const emailMessage = computed(() => {
  if (!emailTouched.value) return ''
  if (!email.value) return '邮箱不能为空'
  if (!emailValid.value) return '邮箱格式不正确'
  return '邮箱格式正确'
})

// 手机号验证（必填）
const phoneValid = computed(() => {
  if (!phone.value) return false
  return /^1[3-9]\d{9}$/.test(phone.value)
})
const phoneMessage = computed(() => {
  if (!phoneTouched.value) return ''
  if (!phone.value) return '手机号不能为空'
  if (!phoneValid.value) return '手机号格式不正确'
  return '手机号格式正确'
})

// 所有必填项都有效
const allValid = computed(() => {
  return usernameValid.value && passwordValid.value && password2Valid.value && emailValid.value && phoneValid.value
})

// 提交注册
async function handleRegister() {
  if (!allValid.value) return
  message.value = ''
  try {
    const res = await fetch('/api/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username.value,
        password: password.value,
        email: email.value,
        phone: phone.value
      })
    })
    const data = await res.json()
    if (res.ok) {
      emit('register-success')
    } else {
      message.value = data.detail || '注册失败'
    }
  } catch (e) {
    message.value = '网络错误，请稍后重试'
  }
}
</script>

<style scoped>
.register-page {
  display: flex;
  justify-content: center;
  padding-top: 30px;
  padding-bottom: 50px;
}
.register-box {
  width: 420px;
  padding: 32px;
  border: 1px solid #e8e8e8;
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}
.register-box h2 {
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
  border: 2px solid #ccc;
  border-radius: 6px;
  font-size: 0.95em;
  outline: none;
  transition: border-color 0.3s;
  box-sizing: border-box;
}
.form-group input.error-border {
  border-color: #ef4444;
}
.form-group input.success-border {
  border-color: #22c55e;
}
.form-group input:focus {
  border-color: #1a56db;
}

/* 密码强度条 */
.pwd-wrapper {
  position: relative;
  display: inline-block;
  width: 100%;
}
.toggle-pwd {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: #1a56db;
  cursor: pointer;
  font-size: 14px;
  user-select: none;
}
.password-bar {
  width: 100%;
  height: 8px;
  background: #eee;
  border-radius: 4px;
  margin: 8px 0 5px;
}
.password-bar-fill {
  height: 100%;
  border-radius: 4px;
  width: 0;
  transition: width 0.3s ease, background-color 0.3s ease;
}
.password-bar-fill.strength-weak {
  width: 33%;
  background-color: #ef4444;
}
.password-bar-fill.strength-medium {
  width: 66%;
  background-color: #f59e0b;
}
.password-bar-fill.strength-strong {
  width: 100%;
  background-color: #22c55e;
}

/* 提示文字 */
.tip {
  margin-top: 6px;
  font-size: 13px;
  min-height: 18px;
}
.tip.error { color: #ef4444; }
.tip.success { color: #22c55e; }

/* 按钮 */
.btn-register {
  width: 100%;
  padding: 12px;
  background: #22c55e;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 16px;
  cursor: pointer;
  margin-top: 10px;
  transition: background 0.2s;
}
.btn-register:hover:not(:disabled) {
  background: #16a34a;
}
.btn-register:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 切换链接 */
.link-to-login,
.link-to-register {
  text-align: center;
  font-size: 0.9em;
  color: #666;
  margin-top: 16px;
}
.link-to-login a,
.link-to-register a {
  color: #1a56db;
  text-decoration: none;
}
.link-to-login a:hover,
.link-to-register a:hover {
  text-decoration: underline;
}
</style>
