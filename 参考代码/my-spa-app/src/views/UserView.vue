<template>
  <div class="user-layout">
    <aside class="user-sidebar">
      <h2>用户中心</h2>
      <nav class="user-nav">
        <router-link to="/user/profile" active-class="active">个人资料</router-link>
        <router-link to="/user/posts" active-class="active">我的文章</router-link>
        <router-link to="/user/orders" active-class="active">我的订单</router-link>
      </nav>
    </aside>
    <main class="user-content">
      <router-view />
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
.user-sidebar {
  width: 180px;
  flex-shrink: 0;
}
.user-sidebar h2 {
  font-size: 1.1em;
  margin-bottom: 12px;
  color: #333;
}
.user-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.user-nav a {
  padding: 10px 14px;
  border-radius: 6px;
  color: #666;
  text-decoration: none;
  font-size: 0.92em;
  transition: background 0.15s, color 0.15s;
}
.user-nav a:hover,
.user-nav a.active {
  background: #e8f5e9;
  color: #42b883;
  font-weight: 500;
}
.user-content {
  flex: 1;
  min-height: 300px;
}
</style>
