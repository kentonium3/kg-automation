# TEMPLATE: Spec-Kitty Feature Specification Input

**Version**: 1.0
**Date**: 2026-01-12
**Purpose**: Standard format for creating spec-kitty feature specifications

---

## About This Template

This template defines the standard format for feature specifications that serve as inputs to the spec-kitty workflow. The format was established based on F049 (Import/Export System - Phase 1) as the reference implementation.

### Key Principles

**Focus on WHAT/WHY, not HOW:**
- Specify WHAT the system must do (requirements)
- Explain WHY it's needed (business context)
- Point to WHERE patterns exist (discovery)
- Define WHEN it's complete (success criteria)
- **Let spec-kitty workflow determine HOW** (planning phase)

**Trust the Spec-Kitty Workflow:**
```
specify → plan → tasks → implement → review → accept → merge
   ↓        ↓       ↓         ↓          ↓        ↓
 (WHAT)  (HOW)  (effort)  (build)    (test)  (validate)
```

**What NOT to Include:**
- ❌ Time estimates (tasks phase handles this)
- ❌ File lists to modify (planning phase identifies these)
- ❌ Testing instructions (review phase handles this)
- ❌ Implementation code examples (planning/implement phases)
- ❌ Prescriptive UI designs (state requirements, not implementation)

---

## Template Structure

```
# F0XX: [Feature Name]

**Version**: 1.0
**Priority**: [HIGH | MEDIUM | LOW]
**Type**: [Service Layer | UI Enhancement | Full Stack | etc.]

---

## Executive Summary

[2-3 sentences describing what's broken/missing and what this spec fixes]

Current gaps:
- ❌ [Gap 1]
- ❌ [Gap 2]
- ❌ [Gap 3]

This spec [summarize solution in one sentence].

---

## Problem Statement

**Current State (INCOMPLETE):**
```
[Visual tree showing what exists and what's missing]
Component A
├─ ✅ Working feature 1
├─ ✅ Working feature 2
└─ ❌ Missing feature 3

Component B
└─ ❌ DOESN'T EXIST
```

**Target State (COMPLETE):**
```
[Visual tree showing desired end state]
Component A
└─ ✅ All features working

Component B
└─ ✅ Fully implemented
```

---

## CRITICAL: Study These Files FIRST

**Before implementation, spec-kitty planning phase MUST read and understand:**

1. **[Component/Pattern 1]**
   - Find [existing implementation]
   - Study [pattern to copy]
   - Note [important details]

2. **[Component/Pattern 2]**
   - Find [related service]
   - Understand [how it works]
   - Note [validation rules]

3. **[Component/Pattern 3]**
   - Find [UI implementation]
   - Study [existing patterns]
   - Note [user workflows]

---

## Requirements Reference

This specification implements:
- **FR-X**: [Requirement name from requirements doc]
- **FR-Y**: [Another requirement]
- **NFR-Z**: [Non-functional requirement]

From: `docs/requirements/req_[component].md` (vX.Y)

---

## Functional Requirements

### FR-1: [Requirement Name]

**What it must do:**
- [Action 1]
- [Action 2]
- [Action 3]

**Pattern reference:** [Point to existing pattern to study/copy]

**Success criteria:**
- [ ] [Concrete outcome 1]
- [ ] [Concrete outcome 2]
- [ ] [Concrete outcome 3]

---

### FR-2: [Requirement Name]

**What it must do:**
- [Action 1]
- [Action 2]

**Pattern reference:** [Point to existing pattern]

**Business rules:**
- [Rule 1]
- [Rule 2]

**Success criteria:**
- [ ] [Outcome 1]
- [ ] [Outcome 2]

---

[Repeat FR-X pattern for all functional requirements]

---

## Out of Scope

**Explicitly NOT included in this feature:**
- ❌ [Feature deferred - reason]
- ❌ [Feature not needed - reason]
- ❌ [Separate feature - reason]

---

## Success Criteria

**Complete when:**

### [Functional Area 1]
- [ ] [Specific outcome]
- [ ] [Specific outcome]
- [ ] [Specific outcome]

### [Functional Area 2]
- [ ] [Specific outcome]
- [ ] [Specific outcome]

### [Functional Area 3]
- [ ] [Specific outcome]
- [ ] [Specific outcome]

### Quality
- [ ] [Code quality standard]
- [ ] [Error handling standard]
- [ ] [Pattern consistency standard]

---

## Architecture Principles

### [Architecture Aspect 1]

**[Principle Name]:**
- [Description]
- [Rationale]

### [Architecture Aspect 2]

**[Principle Name]:**
- [Description]
- [Rationale]

### Pattern Matching

**[Pattern A] must match [Pattern B] exactly:**
- [Aspect 1]
- [Aspect 2]
- [Aspect 3]

---

## Constitutional Compliance

✅ **Principle I: [Principle Name]**
- [How this spec complies]

✅ **Principle II: [Principle Name]**
- [How this spec complies]

✅ **Principle III: [Principle Name]**
- [How this spec complies]

[Continue for all relevant constitutional principles]

---

## Risk Considerations

**Risk: [Risk description]**
- [Context/impact]
- [Mitigation approach without prescribing implementation]

**Risk: [Risk description]**
- [Context/impact]
- [Mitigation approach]

---

## Notes for Implementation

**Pattern Discovery (Planning Phase):**
- Study [existing pattern A] → apply to [new component]
- Study [existing pattern B] → apply to [new component]
- Study [service X] → understand [requirement Y]

**Key Patterns to Copy:**
- [Pattern A] → [Pattern B] (exact parallel)
- [Pattern C] structure → [Pattern D] structure

**Focus Areas:**
- [Critical implementation consideration 1]
- [Critical implementation consideration 2]
- [Critical implementation consideration 3]

---

**END OF SPECIFICATION**
```

---

## Section Descriptions

### Executive Summary
**Purpose**: Quick overview of problem and solution  
**Length**: 3-5 bullet points + 1 sentence summary  
**Audience**: Anyone needing context at a glance

### Problem Statement
**Purpose**: Visual comparison of current vs target state  
**Format**: Tree diagrams with ✅/❌ indicators  
**Key**: Make gaps immediately obvious

### Study These Files First
**Purpose**: Guide spec-kitty planning phase to patterns  
**Content**: Where to find implementations to study/copy  
**Benefit**: Accelerates research phase, promotes consistency

### Functional Requirements (FR-X)
**Purpose**: Concrete checklist of required functionality  
**Structure**: 
- What it must do (requirements)
- Pattern reference (discovery pointer)
- Success criteria (acceptance tests)

**Key**: Each FR is independently verifiable

### Out of Scope
**Purpose**: Explicit boundaries to prevent scope creep  
**Content**: What's NOT included and why  
**Benefit**: Keeps planning phase focused

### Success Criteria
**Purpose**: Comprehensive checklist for accept phase  
**Content**: Grouped by functional area  
**Note**: Some redundancy with FR success criteria is intentional (emphasis)

### Architecture Principles
**Purpose**: Document types, modes, patterns  
**Content**: High-level structure without implementation  
**Key**: Provide context without prescribing HOW

### Constitutional Compliance
**Purpose**: Show alignment with project principles  
**Content**: Map spec to constitution principles  
**Benefit**: Ensures consistency with project values

### Risk Considerations
**Purpose**: Context for planning phase  
**Content**: What could go wrong and general mitigation approach  
**Key**: Don't prescribe specific solutions

### Notes for Implementation
**Purpose**: Guide pattern discovery  
**Content**: Pointers to existing patterns to study  
**Key**: Focus on WHERE to look, not WHAT to implement

---

## Writing Guidelines

### DO ✅

**Be explicit about requirements:**
- "Must support importing materials catalog"
- "Must validate purchases have positive quantities"
- "Must resolve material_slug to material_id"

**Point to patterns for discovery:**
- "Study how ingredients.json export works, copy for materials"
- "Pattern reference: view_products.json structure"
- "Follow _import_ingredients() pattern exactly"

**Define clear success criteria:**
- "Materials import creates records in database"
- "Materials display in Materials tab after import"
- "Slug resolution works correctly"

**State UI requirements, not implementation:**
- "UI must clearly distinguish 3 export types"
- "UI must auto-detect file format"
- "UI should solve: user confused about which export to use"

**Use visual tree format for current/target state:**
```
Component
├─ ✅ Working
└─ ❌ Broken
```

### DON'T ❌

**Don't estimate effort:**
- ❌ "Part 1: Full backup expansion (2 hours)"
- ✅ Leave blank - tasks phase estimates

**Don't list files to modify:**
- ❌ "Modify: export_service.py, import_service.py"
- ✅ Planning phase identifies files

**Don't prescribe implementation:**
- ❌ "Create method: def export_materials(self, output_dir)"
- ✅ "Must export materials following ingredients pattern"

**Don't include code examples:**
- ❌ 50-line code snippets showing exact implementation
- ✅ "Study _import_ingredients, copy pattern"

**Don't write testing instructions:**
- ❌ "Testing Checklist: [ ] Test A, [ ] Test B"
- ✅ Success criteria sufficient - review phase tests

**Don't design UI implementation:**
- ❌ "Add ctk.CTkRadioButton at line 45 with variable export_type_var"
- ✅ "UI must allow user to select between 3 export types"

---

## Example: Good vs Bad Functional Requirement

### ❌ BAD (Too Prescriptive)

```markdown
### FR-1: Export Materials

**Implementation:**
Add this method to ExportService class in src/services/export_service.py:

```python
def _export_materials(self, output_dir: str):
    """Export materials to JSON"""
    materials = material_catalog_service.get_all_materials()
    export_data = []
    for material in materials:
        export_data.append({
            "slug": material.slug,
            "display_name": material.display_name,
            ...
        })
    with open(os.path.join(output_dir, "materials.json"), 'w') as f:
        json.dump(export_data, f, indent=2)
```

**Testing:**
- [ ] Run test_export_materials()
- [ ] Verify materials.json created
- [ ] Check JSON structure matches ingredients.json

**Estimated effort:** 30 minutes
```

**Problems:**
- Prescribes exact implementation (planning phase job)
- Includes code (implement phase job)
- Lists files to modify (planning phase discovers)
- Testing instructions (review phase job)
- Time estimate (tasks phase job)

### ✅ GOOD (Requirements Focused)

```markdown
### FR-1: Complete Full Backup Export

**What it must do:**
- Export ALL 14 entities (add missing 8: materials, material_products, material_units, material_purchases, finished_goods, events, production_runs, consumption_records)
- Create timestamped folder with manifest.json
- Use slug-based references (not database IDs)
- Include entity counts in manifest for validation

**Pattern reference:** Study how ingredients.json export works, copy for materials entities

**Success criteria:**
- [ ] Backup folder contains all 14 entity files
- [ ] Manifest includes all counts
- [ ] Empty entities export as empty arrays (not skipped)
```

**Why it's good:**
- States WHAT (requirements)
- Points to WHERE (pattern discovery)
- Defines WHEN (success criteria)
- Lets spec-kitty determine HOW

---

## Reference Implementation

**See:** `F049_import_export_phase1.md` (v4.0)

This spec demonstrates the template in practice:
- 7 functional requirements (FR-1 through FR-7)
- Clear current vs target state
- Pattern references throughout
- Comprehensive success criteria
- No prescriptive implementation
- Constitutional compliance
- Risk considerations

**Use F049 as the reference example when creating new specs.**

---

## Common Patterns

### Pattern: Service Layer Enhancement

```markdown
## CRITICAL: Study These Files FIRST

1. **Existing service**
   - Find current implementation
   - Study method patterns
   - Note validation approach

2. **Related services**
   - Find dependencies
   - Understand interactions
   - Note business rules

### FR-X: Add [Feature] to [Service]

**What it must do:**
- [Action using service]
- [Validation requirement]
- [Business rule enforcement]

**Pattern reference:** Study [existing_method], copy for [new_feature]

**Success criteria:**
- [ ] [Service outcome]
- [ ] [Validation works]
- [ ] [Business rule enforced]
```

### Pattern: UI Enhancement

```markdown
### FR-X: Enhance [UI Component]

**What it must do:**
- UI must [user capability]
- UI should solve: [current problem]
- UI must provide: [user feedback]

**UI Requirements:**
- [Required capability 1]
- [Required capability 2]
- [Required capability 3]

**Note:** Exact UI design (dropdowns vs radios, etc.) determined during planning phase. Focus on WHAT the UI needs to accomplish, not HOW to implement it.

**Success criteria:**
- [ ] User can [action]
- [ ] User understands [purpose]
- [ ] [Workflow] is clear and intuitive
```

### Pattern: Pattern Matching Requirement

```markdown
### FR-X: Add Support for [Entity]

**What it must do:**
- [Core functionality]
- [Validation/business rules]
- [Integration points]

**Pattern reference:** Study [existing_entity] implementation, copy exactly for [new_entity]

**Pattern Matching:**
[New Entity] must match [Existing Entity] exactly:
- Same service call structure
- Same validation approach
- Same error handling
- Same naming conventions

**Success criteria:**
- [ ] [New entity] behavior matches [existing entity]
- [ ] Pattern consistency verified
- [ ] No code duplication
```

---

## Checklist for Spec Authors

Before submitting spec to spec-kitty, verify:

### Structure
- [ ] Executive Summary present (2-3 sentences + bullets)
- [ ] Problem Statement with current vs target trees
- [ ] "Study These Files First" section with discovery pointers
- [ ] FR-X sections for all functional requirements
- [ ] Out of Scope section with explicit boundaries
- [ ] Success Criteria comprehensive checklist
- [ ] Constitutional Compliance section
- [ ] Risk Considerations present

### Content Quality
- [ ] Requirements focus on WHAT, not HOW
- [ ] Pattern references point to discovery, don't prescribe
- [ ] Success criteria are concrete and verifiable
- [ ] UI requirements state needs, not implementation
- [ ] Business rules clearly documented
- [ ] Architecture principles provide context

### What's NOT Included
- [ ] No time estimates (let tasks phase handle)
- [ ] No file lists (let planning phase identify)
- [ ] No testing instructions (let review phase handle)
- [ ] No implementation code examples
- [ ] No prescriptive UI designs (dropdowns vs radios, etc.)

### Clarity
- [ ] Visual trees use ✅/❌ effectively
- [ ] Current state accurately described
- [ ] Target state clearly defined
- [ ] Gaps immediately obvious
- [ ] Pattern references clear and specific

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-12 | Initial template based on F049 v4.0 reference implementation |

---

**END OF TEMPLATE**
