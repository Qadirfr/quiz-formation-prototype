# Appariement V23.1 — mise au point et recette

Branche : dev-matching-v23-1-20261121 (base : dev-backup-portable-20261121).

## Ce qui change

- Création manuelle et revue CDPO : contrôle strict des paires au moment de la validation. Format une ligne par association, avec le séparateur gauche => droite ; au moins deux et au plus douze paires. Les doublons normalisés des deux côtés, champs vides et lignes incorrectes sont refusés.
- Imports : la validation des quiz signale les appariements incomplets, dupliqués ou ambigus. Les enregistrements historiques ne sont pas réécrits automatiquement.
- Affichage : la colonne de droite est mélangée de façon déterministe pour une même question et un même contexte de passation, sans changer les correspondances stockées. La version de quiz préparé utilise aussi l'identifiant de tentative.
- Passation : sélection de chaque association obligatoire et interdiction de réutiliser la même réponse de droite. Les réponses invalides sont signalées avant la création d'une tentative autonome et avant l'enregistrement d'une réponse.
- Correction : même règle dans les moteurs principal et V19/V20 : 1 point réparti sur les associations, avec rétroaction par association et explication globale existante. Un complément pédagogique optionnel peut figurer dans chaque objet pair sous la propriété explanation.
- Compatibilité : une question historique à une seule paire reste corrigeable. La création de nouveaux exercices requiert deux paires minimum. Les données existantes ne sont pas migrées.

## Exemple de données

{
  "type": "matching",
  "question": "Associez chaque acteur à son rôle",
  "pairs": [
    {"left": "Responsable du traitement", "right": "Détermine les finalités"},
    {"left": "Sous-traitant", "right": "Agit pour le responsable"},
    {"left": "DPO", "right": "Conseille et contrôle", "explanation": "Sa mission de conseil est distincte de la responsabilité du traitement"}
  ],
  "explanation": "Vérifiez la répartition des responsabilités au titre du RGPD."
}

Pour un CSV ou XLSX industriel, utiliser pairs_json avec le tableau JSON de paires. Les deux colonnes peuvent contenir du texte. Les médias insérés dans chaque paire et le glisser-déposer ne font pas partie de cette version.

## Recette attendue

1. Créer une question d'appariement à trois paires, avec deux réponses explicites et une explication pédagogique. Enregistrer et recharger la banque.
2. Tenter des paires doublonnées, une ligne sans =>, une association incomplète et un exercice à une seule paire. Vérifier l'affichage du refus.
3. Importer un fichier CSV, XLSX et JSON d'appariement. Vérifier que les erreurs empêchent la validation et que le format pairs_json reste réimportable.
4. Passer la question dans un quiz préparé, une session dirigée et un entraînement autonome. Répondre correctement, partiellement et avec une proposition répétée. Vérifier que le score et les commentaires sont cohérents.
5. Revenir sur l'exercice sans changer de tentative. Vérifier la stabilité de l'ordre des propositions. Démarrer une autre tentative et vérifier l'absence de fuite des réponses attendues dans l'interface.
6. Refaire les tests sur mobile et mesurer les temps de réponse par rapport à la branche source pour contrôler l'absence de régression.

## Contrôles automatisés

Le fichier tests/test_matching.py couvre les paires invalides, le mélange stable, la notation partielle, le retour pédagogique et les anciennes questions à une paire. Le workflow .github/workflows/qa-matching.yml compile les sources et exécute les tests existants.

L'exécution réelle du workflow et la recette sur la base PostgreSQL de production doivent encore être confirmées. Ne pas fusionner ou déployer sans ces vérifications.

## Suite

Une V23.2 pourra introduire des appariements images/texte, puis éventuellement un glisser-déposer accessible, après validation du socle textuel.