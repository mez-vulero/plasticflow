# frappe-ui — Vue 3 Component Library Reference

frappe-ui is used for **standalone SPAs** that talk to a Frappe backend (not for Desk forms).
Examples: Frappe Cloud, CRM, Gameplan, Frappe Drive.

## Setup

```bash
npm install frappe-ui
# or
yarn add frappe-ui
```

```javascript
// main.js
import { createApp } from 'vue'
import { FrappeUI, setConfig, frappeRequest } from 'frappe-ui'
import App from './App.vue'
import './index.css'

// Point to your Frappe backend
setConfig('resourceFetcher', frappeRequest)

let app = createApp(App)
app.use(FrappeUI)
app.mount('#app')
```

```javascript
// tailwind.config.js
import preset from 'frappe-ui/src/utils/tailwind.config'
export default {
    presets: [preset],
    content: [
        './index.html',
        './src/**/*.{vue,js,ts}',
        './node_modules/frappe-ui/src/**/*.{vue,js,ts}'
    ]
}
```

---

## createResource — Core Data Fetching

```javascript
import { createResource } from 'frappe-ui'

// Single resource (calls a whitelisted method)
const item = createResource({
    url: 'myapp.api.get_item',
    params: { name: 'ITEM-001' },
    auto: true,                    // fetch immediately
    onSuccess(data) { console.log(data) },
    onError(err) { console.error(err) }
})

// Usage in template
item.fetch()            // manual fetch
item.reload()           // re-fetch with same params
item.data               // response data
item.loading            // boolean
item.error              // error if any

// Update params and re-fetch
item.update({ params: { name: 'ITEM-002' } })
```

```javascript
// List resource
const items = createListResource({
    doctype: 'Item',
    fields: ['name', 'item_name', 'rate'],
    filters: { disabled: 0 },
    orderBy: 'item_name asc',
    pageLength: 20,
    auto: true
})

items.data          // array of rows
items.hasNextPage   // boolean
items.next()        // load next page
items.reload()
items.insert.submit({ item_name: 'New Item', ... })   // create
items.setValue.submit({ name: 'ITEM-001', rate: 200 }) // update
items.delete.submit('ITEM-001')                         // delete
```

---

## Components

### Button

```vue
<Button variant="solid" @click="handler">Save</Button>
<Button variant="outline">Cancel</Button>
<Button variant="ghost" size="sm" :loading="isLoading">Submit</Button>
<Button variant="subtle" icon="plus">Add</Button>
<Button theme="red" variant="solid">Delete</Button>
```

Props: `variant` (solid/outline/ghost/subtle), `size` (sm/md/lg), `icon`, `loading`, `disabled`, `theme`

### Dialog

```vue
<script setup>
import { ref } from 'vue'
import { Dialog } from 'frappe-ui'

const show = ref(false)
</script>

<template>
  <Button @click="show = true">Open</Button>
  <Dialog v-model="show" title="My Dialog" :options="{
    message: 'Are you sure?',
    actions: [
      { label: 'Confirm', variant: 'solid', theme: 'red', onClick: () => { doIt(); show = false } },
      { label: 'Cancel', onClick: () => show = false }
    ]
  }"/>
</template>
```

### FormControl (input fields)

```vue
<FormControl
  type="text"
  label="Customer Name"
  v-model="form.name"
  :required="true"
  placeholder="Enter name..."
/>

<FormControl type="select" label="Status" v-model="form.status"
  :options="[{label: 'Open', value: 'Open'}, {label: 'Closed', value: 'Closed'}]"
/>

<FormControl type="link" label="Customer" v-model="form.customer"
  doctype="Customer"
/>

<FormControl type="date" v-model="form.date" />
<FormControl type="checkbox" v-model="form.active" />
<FormControl type="textarea" v-model="form.notes" />
```

### Badge

```vue
<Badge theme="green">Active</Badge>
<Badge theme="red">Overdue</Badge>
<Badge theme="orange">Pending</Badge>
<Badge theme="gray">Draft</Badge>
```

### Avatar

```vue
<Avatar image="/path/to/image.jpg" label="John Doe" size="lg" />
<!-- size: xs/sm/md/lg/xl/2xl -->
```

### Tooltip

```vue
<Tooltip text="This is a tooltip" placement="top">
  <Button>Hover me</Button>
</Tooltip>
```

### Tabs

```vue
<Tabs v-model="activeTab" :tabs="[
  { name: 'Details', label: 'Details' },
  { name: 'History', label: 'History', count: 5 }
]">
  <template #tab-Details>
    <div>Details content</div>
  </template>
  <template #tab-History>
    <div>History content</div>
  </template>
</Tabs>
```

### ListView

```vue
<ListView
  :columns="[
    { label: 'Name', key: 'name' },
    { label: 'Status', key: 'status', width: '120px' }
  ]"
  :rows="items.data"
  :options="{
    selectable: true,
    showTooltip: true,
    onRowClick: (row) => openDetail(row.name)
  }"
/>
```

### DataTable

```vue
import { DataTable } from 'frappe-ui'

<DataTable :data="rows" :columns="columns" />
```

### FeatherIcon / LucideIcon

```vue
<FeatherIcon name="plus" class="w-4 h-4" />
<!-- name matches feather-icons names: edit, trash, check, x, search, filter... -->
```

---

## Utility Composables

```javascript
import { useDebouncedRefHistory, useInfiniteScroll } from 'frappe-ui'

// Debounced search
import { ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'

const search = ref('')
const debouncedSearch = useDebounceFn(() => {
    items.update({ filters: { item_name: ['like', `%${search.value}%`] } })
}, 300)

watch(search, debouncedSearch)
```

---

## frappeRequest — Direct API Calls

```javascript
import { frappeRequest } from 'frappe-ui'

const result = await frappeRequest({
    url: '/api/method/myapp.api.my_method',
    method: 'POST',
    params: { key: 'value' }
})
```

---

## Vite Config for Frappe Backend Proxy

```javascript
// vite.config.js
export default {
    plugins: [vue()],
    server: {
        port: 8080,
        proxy: {
            '/api': {
                target: 'http://mysite.localhost:8000',
                changeOrigin: true
            },
            '/assets': { target: 'http://mysite.localhost:8000', changeOrigin: true },
            '/files':  { target: 'http://mysite.localhost:8000', changeOrigin: true },
        }
    }
}
```

---

## Starter Boilerplate

```bash
# Official frappe-ui SPA starter
npx degit frappe/frappe-ui-starter my-vue-app
cd my-vue-app
yarn install
yarn dev
```
