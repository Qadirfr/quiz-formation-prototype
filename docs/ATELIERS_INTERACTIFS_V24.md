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
