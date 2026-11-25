# Quiz Formation V23 — Lot 4 : exercices d'analyse visuelle

## Objectif

Permettre à un apprenti de **cliquer sur une ou plusieurs zones d'une image** pour y identifier des anomalies, des contrôles ou des éléments techniques. L'exercice s'utilise dans l'application Streamlit V23 existante, avec la même banque de questions et les mêmes résultats.

Une question du type `image_hotspots` contient une image et des zones normalisées : coordonnées en pourcentage, rayon, statut attendu ou distracteur, libellé et explication pédagogique. Le système ne crée **aucune nouvelle table Supabase**.

## Deux exemples prêts à essayer

Dans **Espace formateur → 1. Source**, déplier **Lot 4 — Analyse visuelle · cliquer sur les zones d'une image** :

1. **SSI — Architecture SI fictive** : l'apprenti doit identifier deux points de vigilance parmi Internet, une application, une base de données et une sauvegarde. Les zones attendues concernent les flux vers la base et les tests de restauration.
2. **RGPD — Parcours fictif de données personnelles** : l'apprenti doit identifier un export non protégé et une durée de conservation excessive, parmi plusieurs étapes.

Les illustrations d'exemple sont créées dans l'application. Elles ne contiennent pas de données clients. Les réponses ne sont pas enregistrées lors de la prévisualisation.

## Création sans code par le formateur

Dans **2. Création manuelle** :

1. Choisir **Analyse visuelle — zones cliquables** comme type de question.
2. Saisir les métadonnées habituelles : formation, domaine, sous-domaine, niveau, consigne, objectifs et remédiation.
3. Dans **Illustration / média**, **Téléverser une image** (PNG, JPG ou WEBP, 2 Mo maximum) ou utiliser une **URL HTTPS**. Un fichier téléversé est conservé dans le JSON de la question, comme les images déjà prises en charge dans V23.
4. Cliquer sur l'image. Saisir le libellé, l'explication et le **rayon de tolérance**. Définir « Zone à repérer » ou « Leurre ». Cliquer sur **Ajouter cette zone**.
5. Répéter jusqu'à constituer de **1 à 6 zones attendues** (avec d'éventuels leurres, 12 zones au maximum), puis utiliser **Prévisualiser / préparer cette question**.
6. Tester comme un apprenti, consulter la correction et ajouter à la banque.

Les coordonnées sont enregistrées en **pourcentages**. Elles restent valables lorsque l'image change de taille à l'écran, notamment sur mobile.

## Import Excel / CSV en nombre

Dans **1. Source → Lot 4**, télécharger **Modèle Excel — zones cliquables** ou le CSV. L'import utilise ensuite le circuit habituel **Import industriel → Analyser le fichier → Prévisualiser → Ajouter directement à la banque**.

**Une ligne représente une zone.** Toutes les lignes ayant le même `visual_id` forment une seule question.

| Colonne | Rôle |
|---|---|
| `visual_id` | Identifiant commun de l'exercice |
| `question` | Consigne donnée à l'apprenti |
| `image_url` | URL HTTPS de l'image, ou `demo:network` / `demo:gdpr` pour les illustrations fictives |
| `zone_id` | Identifiant de zone : Z1, Z2… |
| `zone_label` | Nom de l'élément repéré |
| `x_pct`, `y_pct` | Centre de la zone sur l'image, de 0 à 100 % |
| `radius_pct` | Rayon de tolérance, entre 2 et 25 % |
| `is_target` | `true` pour une zone attendue, `false` pour un leurre |
| `zone_feedback` | Explication du constat ou du point de contrôle |
| `training_scope`, `domain`, `subdomain` | Formation, domaine, sous-domaine |
| `explanation`, `remediation` | Synthèse de correction et conseils de révision |

Il n'y a **aucune cellule JSON** à rédiger. Le fichier Excel possède un onglet **Mode d'emploi**. Pour une illustration privée, le téléversement par l'interface formateur évite de publier l'image sur Internet.

### Modèle et procédure de contrôle

L'import valide le nombre de zones, leurs coordonnées, les libellés, les statuts attendus et l'existence de l'image. Les fichiers incohérents sont refusés avant ajout à la banque.

## Fonctionnement côté apprenti

L'apprenti clique sur l'image. Chaque point sélectionné apparaît sous forme d'un repère numéroté. Il peut **retirer le dernier point** ou **recommencer** sans incidence sur le score.

Lorsqu'il a placé exactement autant de points que le nombre de zones attendues, le bouton de validation devient disponible.

La correction attribue **une fraction du score à chaque zone attendue correctement trouvée**. Une zone est comptée une seule fois, même si l'apprenti clique dessus deux fois. Une sélection sur un leurre ou ailleurs ne donne aucun point. La notation, l'explication et les zones attendues ne sont révélées **qu'après la validation**, y compris en session dirigée.

Les cercles de correction sont dessinés sur les images téléversées ou sur les illustrations intégrées. Avec une image distante, le corrigé donne les libellés et les positions des zones sans télécharger arbitrairement le contenu depuis un serveur externe.

## Contrôles et limites

- **Composant léger** : `streamlit-image-coordinates==0.4.1`, qui transmet le clic et les dimensions affichées.
- **Pas de migration de base** : les champs `media` et `hotspots` sont conservés dans le JSON existant.
- **Données** : images intégrées limitées à 2 Mo et 6 millions de pixels. Les URLs d'image doivent être en HTTPS.
- **Confidentialité** : ne pas uploader d'images clients non anonymisées sans autorisation. Une image téléversée est enregistrée avec le quiz dans la banque existante.
- **Accessibilité** : la sélection sur image est optimisée pour la souris et le toucher. Pour un apprenti ne pouvant pas utiliser de dispositif de pointage, préparer un exercice alternatif d'appariement ou de QCM.
- **Compatibilité** : les anciens quiz, les autres types de questions et les sessions existantes conservent leurs structures et leurs évaluations.

## Recette recommandée

1. Tester le schéma SSI, cliquer les deux points de vigilance, puis regarder la correction.
2. Recommencer et sélectionner un leurre : vérifier le score partiel.
3. Tester le scénario RGPD sur téléphone et sur ordinateur pour confirmer l'indépendance vis-à-vis de la taille d'affichage.
4. Créer une nouvelle question à partir d'une image téléversée et placer au moins deux zones.
5. Télécharger le modèle Excel, modifier un exemple, l'importer, vérifier le rapport et prévisualiser avant l'ajout.
6. Constituer un quiz autonome puis une session dirigée contenant une question visuelle.
7. Rejouer les cinq formats des lots 1–2 et les scénarios du lot 3 pour vérifier l'absence de régression.

### Modules

- Moteur et éditeur : `utils/visual_hotspots.py`
- Modèles et import : `utils/visual_templates.py` et `utils/table_import.py`
- Interface : `app.py`
- Tests : `tests/test_visual_hotspots.py`, `tests/test_visual_templates.py`, `tests/test_visual_v23_integration.py`
