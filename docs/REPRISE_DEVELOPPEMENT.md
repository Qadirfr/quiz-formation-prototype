# Point de reprise — Quiz Formation

État de départ constaté le 21 novembre 2026.

## Référence de travail

- Dépôt : `Qadirfr/quiz-formation-prototype`.
- Branche source : `diagnostic-performance-v23`.
- Commit source : `4396886699d3d53ec8b01459553a5624fcb072f8`.
- Branche de ce lot : `dev-backup-portable-20261121`.

À cette date, la branche source contient 75 commits qui ne sont pas dans `main`. Elle est la base de cette reprise. Repartir de `main` ferait travailler sur une version antérieure. Le lien GitHub Codespaces identifie un environnement de développement associé au dépôt. Il ne fournit pas à lui seul l’adresse ou la configuration d’une application Streamlit déployée.

## Lot réalisé : conserver les données et fiabiliser l’accès formateur

Le nouvel export de sauvegarde est accessible dans l’espace formateur, onglet Export, même lorsqu’aucun quiz n’est chargé. Il lit les neuf tables applicatives connues, les JSON et les médias locaux référencés autorisés. Le manifeste rend les compteurs et les limites contrôlables. Il ne modifie pas les données et ne migre pas le schéma.

Le mot de passe formateur est lu dans l’environnement ou les secrets Streamlit. La valeur de démonstration par défaut est supprimée et un mot de passe absent désactive l’accès. La sauvegarde n’est créée qu’après clic, reste propre à la session et est effacée lors d’une nouvelle tentative, à la demande ou à la déconnexion.

Les fonctions de formatage de cinq listes de sélection ont également été stabilisées. Elles réutilisaient une variable ensuite réaffectée, ce qui pouvait invalider les libellés des quiz ou tentatives lors d’un rechargement de l’interface.

Les validations utilisent des données de test dans des bases temporaires. Aucune base de l’utilisateur ni configuration de production n’a été récupérée ou modifiée pour réaliser ce lot. Le comportement PostgreSQL est simulé dans les tests et doit encore être validé sur une instance dédiée. Le détail des tests et leurs résultats est joint à la proposition de modification GitHub.

### Résultat des vérifications

La commande `python -m pytest tests -q --tb=short` passe : **31 tests réussis**, dont 19 tests du module de sauvegarde et 12 tests d’intégration Streamlit AppTest. Le parcours de démonstration et une passation apprenant avec enregistrement du score sont inclus. Les tests vérifient les octets du ZIP et son bouton de téléchargement. Ils ne simulent pas l’enregistrement du fichier par un navigateur.

Environnement vérifié : Python 3.12.14, Streamlit 1.67.0, pandas 3.1.1 et pytest 9.2.0. Le seul avertissement pytest concerne la dépréciation de PyPDF2 3.0.1. La compilation des fichiers Python modifiés et `git diff --check` passent également.

## Prochains lots et critères de fin

| Priorité | Travail | Critère de fin |
| --- | --- | --- |
| 1 | Identifier le déploiement utilisé et valider la sauvegarde sur cette installation | Adresse de l’application, branche exécutée et mode de base établis. Archive téléchargée et compteurs rapprochés des données existantes, sans exposer les secrets. |
| 2 | Fiabiliser l’identité et les sessions apprenants avant une ouverture publique | Une URL ou une adresse e-mail saisie ne suffit plus à prendre l’identité d’un autre apprenant. Accès aux tentatives et résultats contrôlé côté application, y compris après rechargement. Tests de non-accès entre deux apprenants. |
| 3 | Réaliser une restauration contrôlée | Validation du format et des empreintes, aperçu des changements, vérification des relations et restauration testée dans une base distincte avant toute écriture sur la base utilisée. Pas de remplacement silencieux. |
| 4 | Terminer la correction manuelle des réponses rédigées | Le formateur attribue un score et un retour. Les résultats et compteurs de questions restant à corriger sont recalculés et restent cohérents pour les quiz et les sessions. |
| 5 | Choisir et intégrer la génération IA pour l’hébergement visé | Génération accessible depuis le serveur retenu, clé gardée côté serveur si nécessaire, délais et erreurs maîtrisés, validation pédagogique avant enregistrement des questions. |
| 6 | Recetter le parcours complet avec les supports réels | Import de questions et cas, édition, banque, composition d’une évaluation, passation, correction, résultats, sauvegarde et réouverture vérifiés. |

L’ordre des lots 3 à 6 peut être adapté aux priorités de formation. La sécurisation de l’identité apprenant précède une diffusion large avec des résultats personnels.

## Points à préserver pendant la suite

- Conserver les identifiants, les scénarios partagés, les types de questions et les instantanés des réponses lors de toute évolution du schéma.
- Maintenir le fonctionnement SQLite et PostgreSQL. Un changement de configuration ne doit pas être présenté comme une migration des données.
- Vérifier les données avant et après une migration. Ne pas utiliser un import de quiz pour restaurer une sauvegarde globale.
- Compléter ce document et les tests à chaque lot pour que la reprise du développement ne dépende pas du seul historique de conversation.
