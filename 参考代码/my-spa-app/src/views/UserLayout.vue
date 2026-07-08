<script setup>
import { RouterView, RouterLink } from 'vue-router';
</script>

<template>
  <div class="user-layout">
    <aside class="sidebar">
      <h3>用户中心</h3>
      <nav>
        <RouterLink to="/user/profile">个人资料</RouterLink>
        <RouterLink to="/user/order">我的订单</RouterLink>
        <RouterLink to="/user/settings">安全设置</RouterLink>
      </nav>
    </aside>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.user-layout {
  display: flex;
  max-width: 900px;
  margin: 0 auto;
  padding: 24px 16px;
  gap: 24px;
}
.sidebar {
  width: 180px;
  flex-shrink: 0;
}
.sidebar h3 {
  font-size: 1.1em;
  margin-bottom: 12px;
  color: #333;
}
.sidebar nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sidebar nav a {
  padding: 10px 14px;
  border-radius: 6px;
  color: #666;
  text-decoration: none;
  font-size: 0.92em;
  transition: background 0.15s, color 0.15s;
}
.sidebar nav a:hover,
.sidebar nav a.router-link-active {
  background: #e8f5e9;
  color: #42b883;
  font-weight: 500;
}
.content {
  flex: 1;
  min-height: 300px;
}
</style>
