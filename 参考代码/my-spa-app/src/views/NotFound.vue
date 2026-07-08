<template>
  <div class="not-found">
    <h1 class="code">404</h1>
    <p class="msg">抱歉，你访问的页面不存在</p>
    <router-link to="/" class="home-link">返回首页</router-link>
  </div>
</template>

<script setup>
</script>

<style scoped>
.not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  text-align: center;
}
.code {
  font-size: 6em;
  font-weight: 700;
  color: #42b883;
  margin: 0 0 16px 0;
  letter-spacing: 8px;
}
.msg {
  font-size: 1.2em;
  color: #888;
  margin: 0 0 32px 0;
}
.home-link {
  display: inline-block;
  padding: 12px 28px;
  background: #42b883;
  color: #fff;
  border-radius: 8px;
  text-decoration: none;
  font-size: 0.95em;
  transition: background 0.2s, transform 0.15s;
}
.home-link:hover {
  background: #369e6d;
  transform: translateY(-1px);
}
</style>
