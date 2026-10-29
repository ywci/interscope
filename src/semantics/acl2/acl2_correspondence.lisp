; ISIR.ACL2.acl2_correspondence
;
; Both use the same list-based state, so R-state is identity.  The real
; content is the per-operator correspondence: the lowering's wrapped / bitwise
; ACL2 terms equal the source semantics' `wrap` / `nat-and` / ... terms.
;
;   lowering (isir_to_acl2.py)        source semantics (acl2_semantics.lisp)
;   ------------------------------    --------------------------------------
;   (mod (+ a b) (expt 2 n))          (wrap n (+ a b))
;   (mod (- a b) (expt 2 n))          (wrap n (- (+ (expt 2 n) a) b))
;   (logand a b)                      (nat-and a b)
;   (logior a b)                      (nat-or a b)
;   (logxor a b)                      (nat-xor a b)
;   (mod (ash a b) (expt 2 n))        (wrap n (* a (expt 2 b)))
;   (mod (ash a (- b)) (expt 2 n))    (wrap n (floor a (expt 2 b)))
;
; Comparisons are a trivial bool bridge: the lowering returns ACL2 booleans
; (t/nil), the semantics returns 0/1 via bool-to-nat.

(in-package "ACL2")

;; Loaded after acl2_semantics.lisp (which defines wrap/nat-and/nat-or/nat-xor/
;; bool-to-nat).  Books in this tree are loaded with `ld`, not `include-book`
;; (matching the ACL2 prover backend), so acl2_semantics must already be in the
;; logical world.

;; ------------------------------------------------------------------
;; State + operator support
;; ------------------------------------------------------------------

;; R-state: the lowering's list-based state IS the semantics' state.
(defun R-state (st st2) (equal st st2))

;; The binops the ACL2 correspondence covers (all of them; `partial`/`slice`
;; are separate and handled by isir-eval directly).
(defun supported-binop (op)
  (member-eq op '(add sub and or xor eq neq lt le gt ge shl shr)))

;; ------------------------------------------------------------------
;; Per-operator correspondence
;; ------------------------------------------------------------------

(defthm add-correspondence
  (equal (wrap n (+ a b)) (mod (+ a b) (expt 2 n))))

;; The two's-complement `sub` identity, `(mod (- a b) k) = (mod (- (+ k a) b) k)`.
;; Proved via `mod`'s definition and the floor-of-sum rewrite.
(defthm mod-plus-multiple
  (implies (and (natp n) (integerp x))
           (equal (mod (+ (expt 2 n) x) (expt 2 n)) (mod x (expt 2 n))))
  :hints (("Goal" :in-theory (enable mod |(floor (+ x y) z) where (< 0 z)|))))

(defthm sub-correspondence
  (implies (and (natp n) (integerp a) (integerp b))
           (equal (wrap n (- (+ (expt 2 n) a) b)) (mod (- a b) (expt 2 n))))
  :hints (("Goal" :in-theory (enable wrap mod-plus-multiple))))

(defthm and-correspondence
  (equal (nat-and a b) (logand a b)))

(defthm or-correspondence
  (equal (nat-or a b) (logior a b)))

(defthm xor-correspondence
  (equal (nat-xor a b) (logxor a b)))

(defthm shl-correspondence
  (implies (and (integerp a) (natp b))
           (equal (wrap n (* a (expt 2 b)))
                  (mod (ash a b) (expt 2 n))))
  :hints (("Goal" :in-theory (enable wrap ash))))

(defthm shr-correspondence
  (implies (and (integerp a) (natp b))
           (equal (wrap n (floor a (expt 2 b)))
                  (mod (ash a (- b)) (expt 2 n))))
  :hints (("Goal" :in-theory (enable wrap ash))))

;; Comparison bridge: the semantics returns 0/1, the lowering returns t/nil.
(defthm eq-correspondence
  (equal (bool-to-nat (= a b)) (if (= a b) 1 0)))

(defthm lt-correspondence
  (equal (bool-to-nat (< a b)) (if (< a b) 1 0)))

(defthm le-correspondence
  (equal (bool-to-nat (<= a b)) (if (<= a b) 1 0)))

(defthm gt-correspondence
  (equal (bool-to-nat (> a b)) (if (> a b) 1 0)))

(defthm ge-correspondence
  (equal (bool-to-nat (>= a b)) (if (>= a b) 1 0)))

(defthm neq-correspondence
  (equal (bool-to-nat (not (= a b))) (if (not (= a b)) 1 0)))
