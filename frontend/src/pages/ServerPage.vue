<script setup lang="ts">
// Настройки сервера (только суперадмин): smarthost, TLS-политики, правила доступа SMTP, параметры служб.
// Содержимое вкладки монтируется только когда она активна.
import { ref } from 'vue'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'
import SmarthostTab from '@/pages/server/SmarthostTab.vue'
import TlsPoliciesTab from '@/pages/server/TlsPoliciesTab.vue'
import AccessRulesTab from '@/pages/server/AccessRulesTab.vue'
import ParamsTab from '@/pages/server/ParamsTab.vue'

type TabKey = 'smarthost' | 'tls' | 'access' | 'params'

const tabs: { key: TabKey; label: string; icon: string }[] = [
  { key: 'smarthost', label: 'Исходящая почта', icon: 'pi pi-send' },
  { key: 'tls', label: 'TLS к получателям', icon: 'pi pi-lock' },
  { key: 'access', label: 'Доступ SMTP', icon: 'pi pi-filter' },
  { key: 'params', label: 'Параметры', icon: 'pi pi-wrench' },
]

const active = ref<TabKey>('smarthost')
</script>

<template>
  <div>
    <h1 class="page-title">Сервер</h1>
    <Tabs :value="active" @update:value="active = $event as TabKey">
      <TabList>
        <Tab v-for="tab in tabs" :key="tab.key" :value="tab.key">
          <i :class="tab.icon" style="margin-right: 0.4rem" />{{ tab.label }}
        </Tab>
      </TabList>
      <TabPanels>
        <TabPanel value="smarthost"><SmarthostTab v-if="active === 'smarthost'" /></TabPanel>
        <TabPanel value="tls"><TlsPoliciesTab v-if="active === 'tls'" /></TabPanel>
        <TabPanel value="access"><AccessRulesTab v-if="active === 'access'" /></TabPanel>
        <TabPanel value="params"><ParamsTab v-if="active === 'params'" /></TabPanel>
      </TabPanels>
    </Tabs>
  </div>
</template>
