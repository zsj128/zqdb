<template>
  <div class="posts-page">
    <h3>我的文章</h3>
    <ul class="post-list">
      <li v-for="(post, i) in posts" :key="i">{{ post }}</li>
    </ul>
  </div>
</template>

<script setup>
const posts = ['Vue入门指南', 'Axios实战教程', 'Vue Router详解']
</script>

