import type { Product } from "./domain";

/**
 * The category chips when the warehouse taxonomy is on (`?categorias=warehouse`, or a build with
 * `VITE_CATEGORIES_WAREHOUSE=1`): the departments present in the snapshot, largest first, so a chip never
 * leads to an empty list and the row stays close to today's size (the warehouse has ten departments in
 * use, against the nine keyword categories it replaces).
 *
 * Products the Cosmos tree has no node for - and products scraped after the last warehouse run - have no
 * `category_department`. They are deliberately not guessed into a chip: they keep their keyword `category`
 * and stay reachable through "Todas" and search.
 */
export function departmentsOf(products: Product[]): string[] {
  const counts = new Map<string, number>();
  for (const product of products) {
    const department = product.category_department;
    if (!department) continue;
    counts.set(department, (counts.get(department) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "pt-BR"))
    .map(([department]) => department);
}

/** Whether `product` belongs to the department a chip selected. */
export function inDepartment(product: Product, department: string): boolean {
  return product.category_department === department;
}
