<script setup>
import { ref, watch } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import HelloWorld from './components/HelloWorld.vue'

const router = useRouter()

const isLoggedIn = ref(!!localStorage.getItem('token'))

router.afterEach(() => {
  isLoggedIn.value = !!localStorage.getItem('token')
})

const logout = () => {
  localStorage.removeItem('token')
  isLoggedIn.value = false
  router.replace('/')
}
</script>

<template>
  <header>
    <img alt="Vue logo" class="logo" src="@/assets/logo.svg" width="125" height="125" />
    <div class="wrapper">
      <HelloWorld msg="You did it!" />
      <nav>
        <RouterLink to="/">Home</RouterLink>
        <RouterLink to="/about">About</RouterLink>
        <RouterLink to="/articles">Articles</RouterLink>
        <RouterLink to="/users">Users</RouterLink>
        <RouterLink to="/user">User</RouterLink>
        <RouterLink to="/contact">Contact</RouterLink>
        <template v-if="!isLoggedIn">
          <RouterLink to="/login">登入</RouterLink>
        </template>
        <button v-else @click="logout">退出</button>
      </nav>
    </div>
  </header>

  <RouterView />
</template>

<style scoped>
header {
  line-height: 1.5;
  max-height: 100vh;
}
.router-link-active { color: #000; font-weight: bold; }
.logo { display: block; margin: 0 auto 2rem; }
nav {
  width: 100%;
  font-size: 12px;
  text-align: center;
  margin-top: 2rem;
}
nav a.router-link-exact-active { color: var(--color-text); }
nav a.router-link-exact-active:hover { background-color: transparent; }
nav a { display: inline-block; padding: 0 1rem; border-left: 1px solid var(--color-border); }
nav a:first-of-type { border: 0; }
nav button {
  display: inline-block;
  padding: 0 1rem;
  border: none;
  background: #42b883;
  color: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
}
@media (min-width: 1024px) {
  header { display: flex; place-items: center; padding-right: calc(var(--section-gap) / 2); }
  .logo { margin: 0 2rem 0 0; }
  header .wrapper { display: flex; place-items: flex-start; flex-wrap: wrap; }
  nav { text-align: left; margin-left: -1rem; font-size: 1rem; padding: 1rem 0; margin-top: 1rem; }
}
</style>
