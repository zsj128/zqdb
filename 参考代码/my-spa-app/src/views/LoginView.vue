<template>
  <div>
    <h2>账号登录</h2>
    <input v-model="username" placeholder="用户名" />
    <br>
    <input v-model="password" type="password" placeholder="密码" />
    <br>
    <button class="btn-login" @click="login">登录</button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')

const login = () => {
  // 模拟登录成功
  if (username.value && password.value) {
    // 把token存入本地存储
    localStorage.setItem('token', 'user-token-666')
    // 读取要返回的页面，没有就默认首页
    const returnUrl = route.query.redirect || '/'
    router.replace(returnUrl)
  }
}
</script>

<style>

</style>