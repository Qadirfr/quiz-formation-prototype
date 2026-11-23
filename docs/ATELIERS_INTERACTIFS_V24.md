# Ateliers interactifs — Quiz Formation V24 (lot 1)

## Objectif

Transformer deux types de questions existants en activités par **cartes cliquables**, sans changer le format des questions ni celui des réponses sauvegardées. Les exercices sont utilisables dans les quiz autonomes et dans les sessions dirigées par le formateur.

Cette version ne comporte **pas encore de glisser-déposer** : les cartes se manipulent par des boutons. Cette approche fonctionne aussi au clavier, ne demande pas de composant tiers et évite de rompre la passation dans les formulaires Streamlit.

## 1. Remise en ordre : construire une séquence

Dans l'espace formateur, ouvre **Création manuelle**, sélectionne **Ordonnancement**, saisis un élément par ligne et indique l'ordre attendu avec les lettres A, B, C, etc. Chaque lettre doit apparaître une seule fois. En mode apprenant :

1. Les cartes sont mélangées et ne montrent pas l'ordre corrigé.
2. L'apprenant clique sur les cartes dans l'ordre de son choix.
3. Il peut les monter, les descendre ou les retirer, puis recommencer.
4. La jauge affiche le nombre de cartes placées.
5. **Valider mes réponses** enregistre une liste de lettres, comme avant la refonte.

**Exemple d'atelier d'audit** :

- Question : « Remets dans l'ordre les étapes d'un contrôle de cohérence d'un dossier. »
- A : « Documenter la conclusion »
- B : « Définir le point à vérifier »
- C : « Recueillir les pièces utiles »
- D : « Comparer les pièces aux critères »
- Ordre attendu à saisir : **BCDA**
- Explication : « On définit d'abord le contrôle, puis on recueille les preuves, on les confronte aux critères et on documente le résultat. »

## 2. Appariement : relier deux colonnes

Dans **Création manuelle**, sélectionne **Appariement**, puis saisis au moins deux paires sous la forme **gauche => droite**. Les termes de gauche doivent être distincts.

En mode apprenant :

1. Les cartes de réponse sont mélangées.
2. L'apprenant sélectionne une carte à gauche puis sa correspondance à droite.
3. Une carte de droite déjà utilisée n'est plus proposée, mais le lien peut être modifié.
4. Une jauge affiche le nombre d'associations réalisées.
5. La réponse finale reste un dictionnaire **terme gauche → terme droit**, exploitable par la correction existante.

**Exemple d'atelier d'audit** :

- « Risque => Événement susceptible d'empêcher l'atteinte d'un objectif »
- « Contrôle => Mesure conçue pour maîtriser un risque »
- « Preuve => Élément vérifiable attestant l'exécution d'une action »

## Importer des dizaines d'ateliers avec un seul fichier

La branche V24 utilise le **même import industriel** que V23. Il n'existe donc pas de second mécanisme d'écriture en base ni de migration.

- **Format recommandé : Excel (.xlsx)**, modèle `modele_ateliers_interactifs_V24.xlsx`. Le premier onglet **Questions** contient une ligne par exercice. Le second onglet explique les champs.
- **Alternative : CSV UTF-8** avec séparateur point-virgule. Les noms de colonnes sont identiques.
- Taxonomie : `training_scope` (formation), `question_set_type` (type de série), `domain`, `subdomain`, `difficulty`, `cognitive_level`, `learning_objective`, `competency` et `concept_evaluated`.
- Énoncé : `type` = `ordering` ou `matching`, et `question`.
- Remise en ordre : `item_1` à `item_6` (éléments proposés), `correct_order` (lettres dans l'ordre attendu). Exemple pour quatre éléments : `BCDA`.
- Appariement : `pair_1_left`/`pair_1_right` à `pair_6_left`/`pair_6_right`. Les termes des deux colonnes doivent être distincts pour éviter l'ambiguïté.
- Feedback et suivi : `explanation` (correction détaillée), `remediation` (modalités ou pistes de révision), `source_excerpt` (référence). `case_id`, `context_title` et `context_text` permettent de rattacher plusieurs questions à un cas pratique.

**Dans l'application principale :** Espace formateur → **1. Source** → **Import industriel — CSV / Excel / JSON** → télécharger le modèle V24 → compléter → uploader → **Analyser le fichier**. Le rapport signale les erreurs bloquantes. Il est possible de **prévisualiser les cartes sans rien enregistrer**, puis de choisir **Ajouter directement à la banque**. Les doublons sont ignorés selon le mécanisme actuel.

**Dans une application de démonstration distincte :** déployer la branche `diagnostic-performance-v23` avec `interactive_demo_app.py` comme fichier principal. Elle ne se connecte pas à Supabase. Tu peux y uploader le même Excel ou CSV et essayer les réponses, mais elle n'enregistre rien. L'application principale `app.py` contient aussi un aperçu formateur accessible sans écrire dans la base.

## Lot 2 — trois ateliers supplementaires

Le lot 2 **complete le lot 1**, sans nouvel environnement Streamlit ni nouvelle base. Tous les exercices peuvent etre crees dans **2. Creation manuelle** ou importes dans **1. Source** a partir du **modele Excel lots 1 et 2**. Ils disposent d'un **apercu apprenti**, sans enregistrement, avant l'ajout a la banque.

### 3. Priorisation des risques par cartes (`priority_ranking`)

- Dans la creation manuelle, saisis au moins deux elements. Choisis `rank_all` pour classer tous les elements ou `top_n` et `top_n=2` pour retenir deux priorites.
- L'apprenti selectionne les cartes puis corrige leur ordre avec les fleches.
- Le formulaire conserve `{"ranking": ["A", "C"], "justification": "..." }`. L'exercice exige une justification si `require_justification=true`.
- **Correction differee** : le classement et la justification sont conserves pour le formateur. Il n'existe pas necessairement une priorisation objectivement unique.

### 4. Texte a trous avec etiquettes (`fill_blank`)

- L'enonce contient un marqueur `[...]` par mot a trouver.
- `correct_answers` contient les mots dans l'ordre des trous, separes par ` | ` dans Excel.
- `word_bank` contient les etiquettes a proposer, dans un ordre quelconque. Tu peux ajouter des distracteurs. Si une bonne reponse est repetee, prevois autant d'etiquettes identiques que d'occurrences.
- L'apprenti choisit un trou puis clique sur une etiquette, peut remplacer ses choix, et valide quand tous les trous sont remplis.
- La correction automatique et les points partiels deja existants sont conserves. Si `word_bank` n'est pas renseigne, **la saisie libre d'origine demeure disponible**.
- Exemple : « Le [...] conseille le responsable du traitement ». Reponse `DPO`. Etiquettes `DPO | auditeur | sous-traitant`.

### 5. Repartition de points (`point_allocation`)

- Renseigne au moins deux elements et `total_points` (ex. 100).
- Des curseurs permettent de faire varier les montants attribues a chaque critere.
- L'ecran affiche en direct le total utilise, le solde restant et un avertissement en cas de depassement.
- **Validation impossible** tant que la somme n'est pas exactement egale au budget ou que la justification requise n'est pas fournie.
- La reponse conserve le schema `{"allocations": {"A": 40, "B": 60}, "total": 100, "justification": "..." }`.
- **Correction differee** : il n'existe pas de repartition unique, et la note automatique reste inchangee.

### Import en lot pour les cinq formats

Le nouveau modele Excel/CSV comprend **neuf exemples**, dont un de chaque nouveaute du lot 2. Les colonnes sont toujours compatibles avec `utils.table_import` :

| Type | Champs utiles |
|---|---|
| `ordering` | `item_1..item_6`, `correct_order` |
| `matching` | `pair_1_left` / `pair_1_right` ... |
| `priority_ranking` | `item_1..item_6`, `ranking_mode`, `top_n`, `require_justification` |
| `fill_blank` | `question` avec `[...]`, `correct_answers` et `word_bank` |
| `point_allocation` | `item_1..item_6`, `total_points`, `require_justification` |

Les champs `training_scope`, `domain`, `subdomain`, `question_set_type`, `learning_objective`, `explanation`, `remediation`, `source_excerpt` restent disponibles. L'import produit un rapport de validation avant la banque de questions.

**Recette apprenti conseillee** : creer un quiz avec une question de chaque format, repondre a une priorisation Top 2, un texte a deux trous avec un distracteur et un budget de 100 points, puis verifier les resultats. Rejouer les trois exercices dans une session dirigee pour confirmer le report de la correction sous le controle du formateur.

## Compatibilité et règles de passation

- Les questions déjà sauvegardées de type **ordering** et **matching** utilisent les cartes lorsqu'elles contiennent au moins deux éléments structurés valides. Sinon, l'interface antérieure reste disponible.
- Les barèmes, explications, remédiations, réponses stockées et restitutions existants restent inchangés.
- Pour un quiz autonome qui contient une activité par cartes, l'écran de réponse utilise un conteneur interactif, pas un formulaire bloquant. Le score n'est enregistré qu'au clic sur **Valider mes réponses**.
- Dans une session dirigée, **Valider ma réponse** demeure obligatoire. La correction reste sous le contrôle du formateur.
- Les cartes conservent leur état par tentative et par participant à une session.
- Il n'y a pas de nouvelle dépendance Python ni de migration de base de données.

## Vérifications

Tests unitaires du module : **14 réussis** localement, dont des simulations de clic, d'annulation et de déplacement. Un test de structure du branchement Streamlit est inclus dans le dépôt. Les tests d'intégration de l'application entière et un essai dans une application Streamlit déployée restent à effectuer.

**Recette manuelle avant déploiement :**

1. Créer deux questions de démonstration avec les exemples ci-dessus.
2. Les ajouter à un quiz préparé et enregistrer ce quiz.
3. En mode apprenant, tester la mise en ordre, la montée/descente, le retrait, l'appariement, la modification d'un lien et la validation.
4. Vérifier que les réponses et scores sont conservés dans la restitution individuelle.
5. Rejouer les deux types de questions dans une session dirigée et vérifier le contrôle formateur de la correction.
6. Tester un quiz ancien ne contenant que des QCM, puis un quiz mixte, pour contrôler l'absence de régression.

## Lot suivant envisagé

Proposer des exercices réellement différents plutôt qu'une nouvelle présentation du QCM : image à zones cliquables, scénarios à embranchements avec conséquences et explications, cartes mémoire de révision, puis éventuellement glisser-déposer. Chaque nouveau type doit avoir son modèle de données, sa saisie formateur, son rendu apprenant, sa correction et ses tests de compatibilité.
