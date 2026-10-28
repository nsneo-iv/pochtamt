<script setup lang="ts">
// Пользовательские правила Sieve: моноширинное поле, пример и ошибка проверки с сервера (422)
import { computed } from 'vue'
import Textarea from 'primevue/textarea'
import Message from 'primevue/message'

const props = defineProps<{ modelValue: string | null; error?: string | null; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string | null] }>()

const text = computed({
  get: () => props.modelValue ?? '',
  set: (v: string) => emit('update:modelValue', v.trim() ? v : null),
})

const example = `require ["fileinto"];
# письма с темой, начинающейся с [Рассылка], — в папку Lists
if header :contains "subject" "[Рассылка]" {
  fileinto "Lists";
}`
</script>

<template>
  <div class="form">
    <div class="form__field">
      <label for="sieve-custom">Правила Sieve</label>
      <Textarea id="sieve-custom" v-model="text" rows="8" auto-resize class="mono" :disabled="disabled" :invalid="!!error" fluid />
      <Message v-if="error" severity="error" :closable="false" size="small">{{ error }}</Message>
      <span class="form__hint">
        Правила выполняются после автоответа и пересылки. Проверяются на сервере при сохранении. Пример:
      </span>
      <pre class="sieve-example mono">{{ example }}</pre>
    </div>
  </div>
</template>

<style scoped>
.sieve-example {
  margin: 0;
  padding: 0.6rem 0.75rem;
  background: var(--app-code-bg);
  border-radius: 6px;
  white-space: pre-wrap;
  color: var(--p-text-muted-color);
}
</style>
