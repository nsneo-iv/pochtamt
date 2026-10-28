<script setup lang="ts">
// Форма пересылки: адреса чипами и тумблер «оставлять копию» (общая для админки и кабинета)
import { computed } from 'vue'
import ToggleSwitch from 'primevue/toggleswitch'
import AutoComplete from 'primevue/autocomplete'
import type { Forward } from '@/api/types'

const props = defineProps<{ modelValue: Forward; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: Forward] }>()

function patch(changes: Partial<Forward>): void {
  emit('update:modelValue', { ...props.modelValue, ...changes })
}

const targets = computed({
  get: () => props.modelValue.targets,
  set: (v: string[]) => patch({ targets: [...new Set(v.map((t) => t.trim().toLowerCase()).filter(Boolean))] }),
})
const keepCopy = computed({ get: () => props.modelValue.keep_copy, set: (v: boolean) => patch({ keep_copy: v }) })
</script>

<template>
  <div class="form">
    <div class="form__field">
      <label for="fw-targets">Пересылать на адреса</label>
      <AutoComplete id="fw-targets" v-model="targets" multiple :typeahead="false" placeholder="адрес и Enter" :disabled="disabled" fluid />
      <span class="form__hint">Введите адрес и нажмите Enter. Пустой список — пересылка выключена.</span>
    </div>
    <div class="form__check">
      <ToggleSwitch v-model="keepCopy" input-id="fw-keep" :disabled="disabled" />
      <label for="fw-keep">Оставлять копию в ящике</label>
    </div>
  </div>
</template>
