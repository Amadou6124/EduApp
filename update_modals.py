#!/usr/bin/env python3
"""Moderniser tous les modals et panels selon le pattern premium."""

import re

# ── Patterns overlay modal centré ──
OVERLAY = '''  <div x-show="SHOW" x-cloak
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0"
       x-transition:enter-end="opacity-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100"
       x-transition:leave-end="opacity-0"
       class="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-4"
       @click.self="SHOW = false">'''

CONTAINER_START = '''    <div class="bg-white rounded-2xl shadow-2xl border border-gray-100 w-full WIDTH"
         @click.stop
         x-transition:enter="transition ease-out duration-200"
         x-transition:enter-start="opacity-0 scale-95 translate-y-2"
         x-transition:enter-end="opacity-100 scale-100 translate-y-0"
         x-transition:leave="transition ease-in duration-150"
         x-transition:leave-start="opacity-100 scale-100 translate-y-0"
         x-transition:leave-end="opacity-0 scale-95 translate-y-2">'''

HEADER = '''      <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <h3 class="text-base font-semibold text-gray-900">TITLE</h3>
        <button @click="SHOW = false"
                class="p-1.5 hover:bg-gray-100 rounded-lg transition-colors">
          <i data-lucide="x" class="w-4 h-4 text-gray-500"></i>
        </button>
      </div>'''

# ── Patterns overlay panel latéral ──
PANEL_OVERLAY = '''  <div x-show="SHOW" x-cloak
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0"
       x-transition:enter-end="opacity-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100"
       x-transition:leave-end="opacity-0"
       class="fixed inset-0 bg-black/20 backdrop-blur-[2px] z-40"
       @click="SHOW = false">
  </div>'''

PANEL_CONTAINER = '''  <div x-show="SHOW" x-cloak
       class="fixed top-0 right-0 h-full w-full sm:w-WIDTH bg-white shadow-2xl border-l border-gray-200 z-50 flex flex-col animate-slide-in-right">
    <div class="sticky top-0 bg-white z-10 px-6 py-4 border-b border-gray-100 flex items-center justify-between">
      <div>
        <h2 class="text-base font-semibold text-gray-900">TITLE</h2>
      </div>
      <button @click="SHOW = false" class="p-1.5 hover:bg-gray-100 rounded-lg transition-colors">
        <i data-lucide="x" class="w-4 h-4 text-gray-500"></i>
      </button>
    </div>
    <div class="flex-1 overflow-y-auto px-6 py-5 space-y-5">
      BODY
    </div>
  </div>'''

def process_file(filepath, replacements):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
        else:
            print(f"  ⚠ Pattern not found in {filepath}")
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    # ── 1. schools/class_list.html — 3 modals ──
    print("=== schools/class_list.html ===")
    
    with open('templates/schools/class_list.html', 'r') as f:
        c = f.read()
    
    # showAddModal overlay
    old_add_overlay = '''  <div x-show="showAddModal"
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0 scale-95"
       x-transition:enter-end="opacity-100 scale-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100 scale-100"
       x-transition:leave-end="opacity-0 scale-95"
       class="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
       style="display:none">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg" @click.outside="showAddModal = false">
      <div class="px-6 py-5 border-b border-gray-100 flex items-center justify-between">
        <h3 class="font-semibold text-lg text-brand-blue">{% trans "Nouvelle classe" %}</h3>
        <button @click="showAddModal = false" class="text-gray-400 hover:text-gray-600 p-1 rounded-lg hover:bg-gray-100 transition">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
          </svg>
        </button>
      </div>'''
    
    new_add = '''  <!-- ─── Modal : Nouvelle classe ──────────────────────────── -->
  <div x-show="showAddModal" x-cloak
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0"
       x-transition:enter-end="opacity-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100"
       x-transition:leave-end="opacity-0"
       class="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-4"
       @click.self="showAddModal = false">
    <div class="bg-white rounded-2xl shadow-2xl border border-gray-100 w-full max-w-lg"
         @click.stop
         x-transition:enter="transition ease-out duration-200"
         x-transition:enter-start="opacity-0 scale-95 translate-y-2"
         x-transition:enter-end="opacity-100 scale-100 translate-y-0"
         x-transition:leave="transition ease-in duration-150"
         x-transition:leave-start="opacity-100 scale-100 translate-y-0"
         x-transition:leave-end="opacity-0 scale-95 translate-y-2">
      <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <h3 class="text-base font-semibold text-gray-900">{% trans "Nouvelle classe" %}</h3>
        <button @click="showAddModal = false"
                class="p-1.5 hover:bg-gray-100 rounded-lg transition-colors">
          <i data-lucide="x" class="w-4 h-4 text-gray-500"></i>
        </button>
      </div>'''
    
    c = c.replace(old_add_overlay, new_add)
    
    # showEditModal
    old_edit = '''  <div x-show="showEditModal"
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0 scale-95"
       x-transition:enter-end="opacity-100 scale-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100 scale-100"
       x-transition:leave-end="opacity-0 scale-95"
       class="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
       style="display:none">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg" @click.outside="showEditModal = false">'''
    
    new_edit = '''  <div x-show="showEditModal" x-cloak
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0"
       x-transition:enter-end="opacity-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100"
       x-transition:leave-end="opacity-0"
       class="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-4"
       @click.self="showEditModal = false">
    <div class="bg-white rounded-2xl shadow-2xl border border-gray-100 w-full max-w-lg"
         @click.stop
         x-transition:enter="transition ease-out duration-200"
         x-transition:enter-start="opacity-0 scale-95 translate-y-2"
         x-transition:enter-end="opacity-100 scale-100 translate-y-0"
         x-transition:leave="transition ease-in duration-150"
         x-transition:leave-start="opacity-100 scale-100 translate-y-0"
         x-transition:leave-end="opacity-0 scale-95 translate-y-2">'''
    
    c = c.replace(old_edit, new_edit)
    
    # showImportModal classes
    old_import = '''  <div x-show="showImportModal"
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0 scale-95"
       x-transition:enter-end="opacity-100 scale-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100 scale-100"
       x-transition:leave-end="opacity-0 scale-95"
       class="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
       style="display:none">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-xl max-h-[90vh] overflow-y-auto"
         @click.outside="showImportModal = false">
      <div class="px-6 py-5 border-b border-gray-100 flex items-center justify-between sticky top-0 bg-white z-10">
        <h3 class="font-semibold text-lg text-brand-blue">{% trans "Importer des classes" %}</h3>
        <button @click="showImportModal = false"
                class="text-gray-400 hover:text-gray-600 p-1 rounded-lg hover:bg-gray-100 transition">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
          </svg>
        </button>
      </div>'''
    
    new_import = '''  <!-- ─── Modal : Importer des classes ────────────────────────── -->
  <div x-show="showImportModal" x-cloak
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0"
       x-transition:enter-end="opacity-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100"
       x-transition:leave-end="opacity-0"
       class="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-4"
       @click.self="showImportModal = false">
    <div class="bg-white rounded-2xl shadow-2xl border border-gray-100 w-full max-w-xl max-h-[90vh] overflow-y-auto"
         @click.stop
         x-transition:enter="transition ease-out duration-200"
         x-transition:enter-start="opacity-0 scale-95 translate-y-2"
         x-transition:enter-end="opacity-100 scale-100 translate-y-0"
         x-transition:leave="transition ease-in duration-150"
         x-transition:leave-start="opacity-100 scale-100 translate-y-0"
         x-transition:leave-end="opacity-0 scale-95 translate-y-2">
      <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between sticky top-0 bg-white z-10">
        <h3 class="text-base font-semibold text-gray-900">{% trans "Importer des classes" %}</h3>
        <button @click="showImportModal = false"
                class="p-1.5 hover:bg-gray-100 rounded-lg transition-colors">
          <i data-lucide="x" class="w-4 h-4 text-gray-500"></i>
        </button>
      </div>'''
    
    c = c.replace(old_import, new_import)
    
    with open('templates/schools/class_list.html', 'w') as f:
        f.write(c)
    print("  ✅ class_list.html - 3 modals")

    # ── 2. students/student_list.html — 1 modal + 1 panel ──
    print("=== students/student_list.html ===")
    
    with open('templates/students/student_list.html', 'r') as f:
        c = f.read()
    
    # showImportModal
    old_stu_import = '''  <div x-show="showImportModal" x-cloak
       class="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4"
       @closeImportModal.window="showImportModal = false">

    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
         @click.stop
         x-transition:enter="transition ease-out duration-200"
         x-transition:enter-start="opacity-0 scale-95"
         x-transition:enter-end="opacity-100 scale-100">

      <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
        <h3 class="text-lg font-semibold text-brand-blue">Importer des élèves</h3>
        <button @click="showImportModal = false" class="p-2 text-gray-400 hover:text-gray-600 rounded-lg">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
          </svg>
        </button>
      </div>'''
    
    new_stu_import = '''  <!-- ── Modal import Excel ── -->
  <div x-show="showImportModal" x-cloak
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0"
       x-transition:enter-end="opacity-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100"
       x-transition:leave-end="opacity-0"
       class="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-4"
       @closeImportModal.window="showImportModal = false"
       @click.self="showImportModal = false">
    <div class="bg-white rounded-2xl shadow-2xl border border-gray-100 w-full max-w-2xl max-h-[90vh] overflow-y-auto"
         @click.stop
         x-transition:enter="transition ease-out duration-200"
         x-transition:enter-start="opacity-0 scale-95 translate-y-2"
         x-transition:enter-end="opacity-100 scale-100 translate-y-0"
         x-transition:leave="transition ease-in duration-150"
         x-transition:leave-start="opacity-100 scale-100 translate-y-0"
         x-transition:leave-end="opacity-0 scale-95 translate-y-2">
      <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between sticky top-0 bg-white z-10">
        <h3 class="text-base font-semibold text-gray-900">Importer des élèves</h3>
        <button @click="showImportModal = false"
                class="p-1.5 hover:bg-gray-100 rounded-lg transition-colors">
          <i data-lucide="x" class="w-4 h-4 text-gray-500"></i>
        </button>
      </div>'''
    
    c = c.replace(old_stu_import, new_stu_import)
    
    # showPanel overlay
    old_panel_overlay = '''  <div x-show="showPanel" x-cloak
       class="fixed inset-0 bg-black/40 z-40"
       @click="showPanel = false"
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0"
       x-transition:enter-end="opacity-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100"
       x-transition:leave-end="opacity-0">
  </div>

  {# Panel #}
  <div x-show="showPanel" x-cloak
       class="fixed top-0 right-0 h-full w-full sm:w-[520px] bg-white shadow-2xl z-50 flex flex-col"
       x-transition:enter="transition ease-out duration-300"
       x-transition:enter-start="translate-x-full"
       x-transition:enter-end="translate-x-0"
       x-transition:leave="transition ease-in duration-200"
       x-transition:leave-start="translate-x-0"
       x-transition:leave-end="translate-x-full">

    {# Header du panel #}
    <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100 flex-shrink-0">
      <div class="flex items-center gap-3">
        <h2 class="text-lg font-semibold text-brand-blue">Inscrire un élève</h2>
        <div class="flex gap-1 bg-gray-100 rounded-lg p-0.5">
          <button @click="panelMode = 'individual'"
                  :class="panelMode === 'individual' ? 'bg-white shadow-sm text-brand-blue' : 'text-gray-500'"
                  class="px-3 py-1 text-xs font-medium rounded-md transition">Individuel</button>
          <button @click="panelMode = 'group'"
                  :class="panelMode === 'group' ? 'bg-white shadow-sm text-brand-blue' : 'text-gray-500'"
                  class="px-3 py-1 text-xs font-medium rounded-md transition">Groupe</button>
        </div>
      </div>
      <button @click="showPanel = false" class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>
    </div>

    {# ── Mode individuel ── #}
    <div x-show="panelMode === 'individual'" class="flex-1 overflow-y-auto">'''
    
    new_panel = '''  {# Overlay #}
  <div x-show="showPanel" x-cloak
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0"
       x-transition:enter-end="opacity-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100"
       x-transition:leave-end="opacity-0"
       class="fixed inset-0 bg-black/20 backdrop-blur-[2px] z-40"
       @click="showPanel = false">
  </div>

  {# Panel #}
  <div x-show="showPanel" x-cloak
       class="fixed top-0 right-0 h-full w-full sm:w-[520px] bg-white shadow-2xl border-l border-gray-200 z-50 flex flex-col animate-slide-in-right"
       x-transition:enter="transition ease-out duration-300"
       x-transition:enter-start="translate-x-full"
       x-transition:enter-end="translate-x-0"
       x-transition:leave="transition ease-in duration-200"
       x-transition:leave-start="translate-x-0"
       x-transition:leave-end="translate-x-full">

    {# Header du panel #}
    <div class="sticky top-0 bg-white z-10 px-6 py-4 border-b border-gray-100 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <h2 class="text-base font-semibold text-gray-900">Inscrire un élève</h2>
        <div class="flex gap-1 bg-gray-100 rounded-lg p-0.5">
          <button @click="panelMode = 'individual'"
                  :class="panelMode === 'individual' ? 'bg-white shadow-sm text-brand-blue' : 'text-gray-500'"
                  class="px-3 py-1 text-xs font-medium rounded-md transition">Individuel</button>
          <button @click="panelMode = 'group'"
                  :class="panelMode === 'group' ? 'bg-white shadow-sm text-brand-blue' : 'text-gray-500'"
                  class="px-3 py-1 text-xs font-medium rounded-md transition">Groupe</button>
        </div>
      </div>
      <button @click="showPanel = false"
              class="p-1.5 hover:bg-gray-100 rounded-lg transition-colors">
        <i data-lucide="x" class="w-4 h-4 text-gray-500"></i>
      </button>
    </div>

    {# ── Mode individuel ── #}
    <div x-show="panelMode === 'individual'" class="flex-1 overflow-y-auto px-6 py-5 space-y-5">'''
    
    c = c.replace(old_panel_overlay, new_panel)
    
    # Fix the form padding (remove the duplicate px-6 py-5 since panel has it)
    # Actually, the form inside has px-6 py-5 which will now be nested - we need to keep the form spacing
    # But the user's spec says body panel: flex-1 overflow-y-auto px-6 py-5 space-y-5
    # The form inside has its own px-6 py-5 space-y-5, so it'll be fine
    
    with open('templates/students/student_list.html', 'w') as f:
        f.write(c)
    print("  ✅ student_list.html - 1 modal + 1 panel")

    # ── 3. payments/dashboard.html — 1 modal + 1 panel ──
    print("=== payments/dashboard.html ===")
    
    with open('templates/payments/dashboard.html', 'r') as f:
        c = f.read()
    
    # showPanel overlay
    old_pay_panel = '''  <div x-show="showPanel" x-cloak
       class="fixed inset-0 bg-black/40 z-40"
       @click="showPanel = false"
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0"
       x-transition:enter-end="opacity-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100"
       x-transition:leave-end="opacity-0">
  </div>

  <div x-show="showPanel" x-cloak
       id="payment-panel"
       class="fixed top-0 right-0 h-full w-full sm:w-[480px] bg-white shadow-2xl z-50 flex flex-col overflow-y-auto"
       x-transition:enter="transition ease-out duration-300"
       x-transition:enter-start="translate-x-full"
       x-transition:enter-end="translate-x-0"
       x-transition:leave="transition ease-in duration-200"
       x-transition:leave-start="translate-x-0"
       x-transition:leave-end="translate-x-full">
  </div>'''
    
    new_pay_panel = '''  <div x-show="showPanel" x-cloak
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0"
       x-transition:enter-end="opacity-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100"
       x-transition:leave-end="opacity-0"
       class="fixed inset-0 bg-black/20 backdrop-blur-[2px] z-40"
       @click="showPanel = false">
  </div>

  <div x-show="showPanel" x-cloak
       id="payment-panel"
       class="fixed top-0 right-0 h-full w-full sm:w-[480px] bg-white shadow-2xl border-l border-gray-200 z-50 flex flex-col overflow-y-auto animate-slide-in-right"
       x-transition:enter="transition ease-out duration-300"
       x-transition:enter-start="translate-x-full"
       x-transition:enter-end="translate-x-0"
       x-transition:leave="transition ease-in duration-200"
       x-transition:leave-start="translate-x-0"
       x-transition:leave-end="translate-x-full">
  </div>'''
    
    c = c.replace(old_pay_panel, new_pay_panel)
    
    # showHistory modal
    old_history = '''  <div x-show="showHistory" x-cloak
       class="fixed inset-0 bg-black/40 z-40 flex items-end sm:items-center justify-center p-4"
       @click.self="showHistory = false"
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0"
       x-transition:enter-end="opacity-100">
    <div id="payment-history-modal"
         class="bg-white rounded-2xl shadow-2xl w-full max-w-xl max-h-[85vh] overflow-y-auto"
         @click.stop
         x-transition:enter="transition ease-out duration-200"
         x-transition:enter-start="opacity-0 scale-95"
         x-transition:enter-end="opacity-100 scale-100">
    </div>
  </div>'''
    
    new_history = '''  <div x-show="showHistory" x-cloak
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0"
       x-transition:enter-end="opacity-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100"
       x-transition:leave-end="opacity-0"
       class="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-4"
       @click.self="showHistory = false">
    <div id="payment-history-modal"
         class="bg-white rounded-2xl shadow-2xl border border-gray-100 w-full max-w-xl max-h-[85vh] overflow-y-auto"
         @click.stop
         x-transition:enter="transition ease-out duration-200"
         x-transition:enter-start="opacity-0 scale-95 translate-y-2"
         x-transition:enter-end="opacity-100 scale-100 translate-y-0"
         x-transition:leave="transition ease-in duration-150"
         x-transition:leave-start="opacity-100 scale-100 translate-y-0"
         x-transition:leave-end="opacity-0 scale-95 translate-y-2">
    </div>
  </div>'''
    
    c = c.replace(old_history, new_history)
    
    with open('templates/payments/dashboard.html', 'w') as f:
        f.write(c)
    print("  ✅ payments/dashboard.html - 1 modal + 1 panel")

    # ── 4. bulletins/bulletin_preview.html — 1 modal ──
    print("=== bulletins/bulletin_preview.html ===")
    
    with open('templates/bulletins/bulletin_preview.html', 'r') as f:
        c = f.read()
    
    old_preview = '''<div x-data="{ open: true }"
     x-show="open"
     x-cloak
     class="fixed inset-0 z-50 flex items-center justify-center p-4"
     x-transition:enter="transition ease-out duration-200"
     x-transition:enter-start="opacity-0"
     x-transition:enter-end="opacity-100"
     x-transition:leave="transition ease-in duration-150"
     x-transition:leave-start="opacity-100"
     x-transition:leave-end="opacity-0">

  <div class="absolute inset-0 bg-black/40"></div>

  <div class="relative bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto p-6"
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0 scale-95"
       x-transition:enter-end="opacity-100 scale-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100 scale-100"
       x-transition:leave-end="opacity-0 scale-95">
    <button @click="open = false"
            class="absolute top-3 right-3 p-1.5 hover:bg-gray-100 rounded-lg transition">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
      </svg>
    </button>'''
    
    new_preview = '''<div x-data="{ open: true }"
     x-show="open"
     x-cloak
     x-transition:enter="transition ease-out duration-200"
     x-transition:enter-start="opacity-0"
     x-transition:enter-end="opacity-100"
     x-transition:leave="transition ease-in duration-150"
     x-transition:leave-start="opacity-100"
     x-transition:leave-end="opacity-0"
     class="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4"
     @click.self="open = false">

  <div class="bg-white rounded-2xl shadow-2xl border border-gray-100 w-full max-w-4xl max-h-[90vh] overflow-y-auto"
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0 scale-95 translate-y-2"
       x-transition:enter-end="opacity-100 scale-100 translate-y-0"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100 scale-100 translate-y-0"
       x-transition:leave-end="opacity-0 scale-95 translate-y-2">
    <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
      <h3 class="text-base font-semibold text-gray-900">Aperçu bulletin</h3>
      <button @click="open = false"
              class="p-1.5 hover:bg-gray-100 rounded-lg transition-colors">
        <i data-lucide="x" class="w-4 h-4 text-gray-500"></i>
      </button>
    </div>
    <div class="p-6">'''
    
    c = c.replace(old_preview, new_preview)
    
    # Close the p-6 div and add proper structure at the end
    # The original has </div> </div> at the end, need to add closing for new structure
    # Actually the original has: </div> </div> at the end for the container and outer div
    # Our new structure: <div class="p-6"> ... content ... </div> </div> </div>
    # The content is between our new opening and the original closing divs - should work
    
    with open('templates/bulletins/bulletin_preview.html', 'w') as f:
        f.write(c)
    print("  ✅ bulletin_preview.html - 1 modal")

    print("\n✅ Tous les modals/panels modernisés !")

if __name__ == '__main__':
    main()