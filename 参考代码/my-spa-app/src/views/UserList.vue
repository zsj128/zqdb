<template>
  <div>
    <h2>用户列表</h2>

    <div v-if="loading">⏳ 加载中...</div>

    <div v-else-if="error" style="color: red;">
      加载失败：{{ error }}
    </div>

    <div v-else class="card-list">
      <div class="card" v-for="user in users" :key="user.id">
        <h3>{{ user.name }}</h3>
        <p>邮箱：{{ user.email }}</p>
        <p>城市：{{ user.address.city }}</p>
        <button class="btn-del" @click="removeUser(user.id)">删除</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const users = ref([])
const loading = ref(false)
const error = ref(null)

async function fetchUsers() {
  loading.value = true
  error.value = null
  try {
    const res = await axios.get('https://jsonplaceholder.typicode.com/users', {
      params: { _limit: 10 }
    })
    users.value = res.data
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const removeUser = (id) => {
  users.value = users.value.filter(u => u.id !== id)
}

onMounted(() => fetchUsers())
</script>

<style scoped>
.card-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.card {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 16px;
}
.card h3 { margin: 0 0 8px; }
.card p { margin: 4px 0; color: #666; font-size: 14px; }
.btn-del {
  margin-top: 10px;
  padding: 4px 14px;
  border: none;
  background: #42b883;
  color: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.btn-del:hover { background: #42b883; }
</style>
