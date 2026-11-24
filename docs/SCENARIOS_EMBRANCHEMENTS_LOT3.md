# Quiz Formation V23 — Lot 3 : scénarios à embranchements

## Finalité

Mettre l'apprenti en situation professionnelle. Il choisit une action, constate ses conséquences, puis poursuit un parcours dont l'étape suivante dépend réellement de sa décision. L'objectif est d'évaluer le jugement, et pas seulement une réponse mémorisée.

**Un scénario représente une seule question de quiz**. Elle peut contenir de 2 à 12 étapes structurées et 2 à 4 décisions par étape. Plusieurs parcours sont possibles. Les boucles, les étapes inaccessibles et les destinations inconnues sont refusées.

## Où tester ?

Dans l'application **Quiz Formation V23 existante**, espace formateur, onglet **1. Source** : ouvrir **Lot 3 — Scénarios à décisions successives · aperçu apprenti sans enregistrer**.

Deux cas sont préchargés :

1. **SSI — Gestion d'un incident** : accès inhabituel à des dossiers clients. Selon la première décision, l'apprenti passe par une gestion maîtrisée de l'alerte ou par une correction de communication précipitée.
2. **Audit IA — RAG pour les réclamations** : une équipe souhaite automatiser l'envoi de réponses. Les décisions conduisent à un pilote maîtrisé ou à une situation de déploiement prématuré.

L'aperçu n'ajoute aucune donnée à la banque ni aux résultats des apprenants.

## Créer un scénario directement

Dans **2. Création manuelle**, choisir **Scénario à décisions successives**. Le formulaire guidé propose trois étapes initiales et deux décisions par étape, avec un exemple modifiable.

Pour chaque étape :

- Décrire la situation présentée à l'apprenti.
- Rédiger de deux à quatre décisions.
- Indiquer pour chaque décision la **prochaine étape**, ou **Terminer**.
- Décrire la **conséquence immédiatement visible**.
- Attribuer une note de pertinence entre 0 % et 100 %.
- Renseigner une **explication corrective**, révélée seulement après validation.

Avant l'ajout, le moteur vérifie que toutes les étapes sont accessibles et qu'aucun chemin ne boucle. Le formateur peut **prévisualiser la passation** avant l'enregistrement.

## Importer plusieurs scénarios via Excel ou CSV

Télécharger **Modèle Excel — scénarios** ou **Modèle CSV — scénarios** dans la rubrique Lot 3 de **1. Source**.

**Une ligne = une décision.** Plusieurs lignes portent le même `scenario_id` et constituent ensemble une question. Les champs principaux sont :

| Colonne | Rôle |
|---|---|
| `scenario_id` | Identifiant commun du scénario, p. ex. `INC-01` |
| `question` | Consigne générale / mission |
| `scenario_start` | Première étape, p. ex. `S1` |
| `node_id` | Identifiant de l'étape présentée |
| `node_prompt` | Situation ou événement observé à cette étape |
| `choice_id` | Identifiant du choix dans l'étape, p. ex. `A` |
| `choice_label` | Action proposée à l'apprenti |
| `next_node` | Étape suivante : `S2`, `S3` ou `END` |
| `consequence` | Conséquence affichée dès que le choix est fait |
| `score` | Pertinence de la décision, de 0 à 1 |
| `rationale` | Explication corrective liée au choix |
| `training_scope`, `domain`, `subdomain` | Classement pédagogique |
| `explanation`, `remediation` | Synthèse et pistes de révision |

L'onglet **Mode d'emploi** du modèle Excel rappelle les règles. Le CSV utilise les mêmes colonnes avec un séparateur point-virgule. Il n'est pas nécessaire de saisir du JSON dans une cellule.

Import dans V23 : **1. Source → Import industriel CSV / Excel / JSON → Analyser le fichier → Prévisualiser → Ajouter directement à la banque**. Le rapport d'import bloque les graphes invalides.

## Scoring et restitution

- Chaque décision porte une note de 0 à 1 définie par le formateur.
- Le score final du scénario est la moyenne des notes des décisions effectivement prises sur le parcours choisi. Une branche courte ou longue est donc évaluée sur ses propres décisions.
- Le score automatique est un **barème pédagogique paramétrable** ; il ne prétend pas qu'une décision professionnelle ait toujours une réponse unique.
- Le score, les explications correctives et la piste de révision sont affichés **après validation**, jamais avant.
- La chronologie du parcours et les conséquences sont conservées dans la réponse du quiz pour les restitutions.
- Dans une **session dirigée**, le formateur garde le contrôle de l'affichage de la correction.
- Les scénarios n'altèrent ni les quiz existants, ni les tables de la base, ni les modèles d'import des lots 1 et 2.

## Recette manuelle avant de poursuivre au lot 4

1. Prévisualiser le scénario SSI en choisissant **A puis A**, puis regarder le résultat.
2. Recommencer en choisissant **B puis A** : vérifier que la deuxième étape est différente.
3. Choisir le scénario RAG, prendre un chemin différent et vérifier les conséquences.
4. Télécharger l'Excel de scénarios, modifier une action et importer le fichier.
5. Vérifier le rapport d'analyse puis l'aperçu, sans ajout, avant de déposer les scénarios dans la banque.
6. Réaliser un quiz avec un scénario et tester aussi une session dirigée.
7. Vérifier les résultats, les explications et l'absence de régression des anciens quiz.

## Code et tests

- Moteur et rendu : `utils/interactive_scenarios.py`
- Format d'import et exemples : `utils/scenario_templates.py`
- Routage dans l'application : `app.py`
- Contrôle des fichiers : `utils/table_import.py`
- Tests : `tests/test_interactive_scenarios.py` et `tests/test_scenario_v23_integration.py`

Toute modification future doit conserver les formats existants et s'appuyer sur la branche `diagnostic-performance-v23`.
