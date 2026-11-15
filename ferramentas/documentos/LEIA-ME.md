# Ferramentas dos documentos da Fase 2

Scripts que mantêm os documentos da pasta "Sistema Physis" (OneDrive) iguais ao sistema. Ficam aqui, no Git, para não se
perderem (antes estavam numa pasta temporária).

| Script | O que faz | Quando rodar |
|---|---|---|
| `gerar_memos.py` | Refaz os 12 memos de `19_Memos_Fase2` (por bloco e "Quem faz o quê") a partir do documento 18, das tarefas e dos kits | Depois de mudar tarefas ou responsáveis |
| `checklist_para_gestao.py` | Gera o arquivo de tarefas da Gestão a partir do documento 18 (versão antiga, de uma tarefa por bloco) | Só se o documento 18 for refeito do zero |
| `seed_sync.py` | Copia as tarefas de `sistema/gestao-fase2-tarefas.json` para a semente embutida na Gestão interna | Depois de mudar o arquivo de tarefas (o teste `test_conta_ui` confere) |
| `backup_arquivos.py` | ZIP com o código (com o trabalho ainda não salvo) e os documentos, em `_backup_arquivos` | Antes de mudanças grandes e ao fim do dia |

A emissão (`ferramentas/emitir_entrega.py`) confere o inventário: se faltar uma página, demo, pacote de cliente, kit, módulo,
documento ou memo pedido, ela para e diz o que falta.
