
**remarque méthodologique** : les colonnes "People List" et "Places list" ont un format différent pour les 10 nouveaux papyrus, donc le notebook ipynb ne fonctionne plus.
Cela tient notamment à ce qu'originellement les noms de personnes (dans "People List") et les noms de lieux (dans "Places List") étaient entre crochets et entre accolades respectivement.
Ce n'est plus le cas pour les 10 nouveaux éléments. Il faut ou bien ajouter manuellement des crochets et des accolades, ou bien modifier légèrement la pipeline de nettoyage

L'idéal serait de modifier directement la colonne People List et Places list plutôt que de deux nouvelles colonnes "People List Processed" et "Places List Processed" en précisant de ne rien faire si on ne trouve aucune accolade ni aucun crochets.
