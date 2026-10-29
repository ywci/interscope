; ISIR.ACL2.refinement
;
; The refinement relation and end-to-end instances.
; Loaded after acl2_semantics.lisp + acl2_correspondence.lisp.
;
;   definedness-preservation  : source step defined => lowering step defined
;   value-refinement          : lowering state = source step's state component
;   refines                   : conjunction of the two
;
; The lowering's step is passed as a concrete VALUE (first-order ACL2), so the
; instance theorems are `(equal (car (isir-step ...)) (lowering-step st))`.

(in-package "ACL2")

;; ------------------------------------------------------------------
;; Refinement predicates
;; ------------------------------------------------------------------

(defun definedness-preservation (sched rules rw mem-w lowering-state st inp mem)
  (implies (not (null (isir-step sched rules rw mem-w st inp mem)))
           (not (null lowering-state))))

(defun value-refinement (sched rules rw mem-w lowering-state st inp mem)
  (implies (not (null (isir-step sched rules rw mem-w st inp mem)))
           (equal (car (isir-step sched rules rw mem-w st inp mem))
                  lowering-state)))

(defun refines (sched rules rw mem-w lowering-state st inp mem)
  (and (definedness-preservation sched rules rw mem-w lowering-state st inp mem)
       (value-refinement sched rules rw mem-w lowering-state st inp mem)))

;; ------------------------------------------------------------------
;; Core-fragment instance: counter `reg 0 := add (read 0) 1`, width 4
;; ------------------------------------------------------------------

(defun counter-add-rules ()
  (list (list 1 (list 'write 0 (list 'add (list 'read 0) 1)))))

(defun counter-add-rw () (list 4))
(defun counter-add-mem-w () (list 1))

;; The lowering's single-cycle step for the counter-add rule.
(defun counter-add-step (st)
  (update-nth 0 (mod (+ (nth 0 st) 1) (expt 2 4)) st))

(defthm counter-add-refines
  (refines :parallel (counter-add-rules) (counter-add-rw) (counter-add-mem-w)
           (counter-add-step st) st nil nil)
  :hints (("Goal"
           :in-theory (enable refines value-refinement definedness-preservation
                              isir-step apply-actions apply-action
                              granted-actions grants map-fireb map-fire
                              all-defined fire rule-cond rule-actions
                              isir-eval binop-eval wrap
                              counter-add-rules counter-add-rw counter-add-mem-w
                              counter-add-step))))

;; ------------------------------------------------------------------
;; GCD-style instance: `reg 0 := sub (read 0) 1`, width 4 (two's complement)
;; ------------------------------------------------------------------

(defun gcd-sub-rules ()
  (list (list 1 (list 'write 0 (list 'sub (list 'read 0) 1)))))

(defun gcd-sub-rw () (list 4))
(defun gcd-sub-mem-w () (list 1))

(defun gcd-sub-step (st)
  (update-nth 0 (mod (- (nth 0 st) 1) (expt 2 4)) st))

(defthm gcd-sub-refines
  (implies (integerp (nth 0 st))
           (refines :parallel (gcd-sub-rules) (gcd-sub-rw) (gcd-sub-mem-w)
                    (gcd-sub-step st) st nil nil))
  :hints (("Goal"
           :in-theory (enable refines value-refinement definedness-preservation
                              isir-step apply-actions apply-action
                              granted-actions grants map-fireb map-fire
                              all-defined fire rule-cond rule-actions
                              isir-eval binop-eval sub-correspondence
                              gcd-sub-rules gcd-sub-rw gcd-sub-mem-w gcd-sub-step))))

;; ------------------------------------------------------------------
;; Arbiter-style instance: `reg 0 := ite (read 0) 0 1`, width 4
;; ------------------------------------------------------------------

(defun arbiter-ite-rules ()
  (list (list 1 (list 'write 0 (list 'ite (list 'read 0) 0 1)))))

(defun arbiter-ite-rw () (list 4))
(defun arbiter-ite-mem-w () (list 1))

(defun arbiter-ite-step (st)
  (update-nth 0 (if (equal (nth 0 st) 0) 1 0) st))

(defthm arbiter-ite-refines
  (refines :parallel (arbiter-ite-rules) (arbiter-ite-rw) (arbiter-ite-mem-w)
           (arbiter-ite-step st) st nil nil)
  :hints (("Goal"
           :in-theory (enable refines value-refinement definedness-preservation
                              isir-step apply-actions apply-action
                              granted-actions grants map-fireb map-fire
                              all-defined fire rule-cond rule-actions
                              isir-eval binop-eval wrap
                              arbiter-ite-rules arbiter-ite-rw arbiter-ite-mem-w
                              arbiter-ite-step))))
