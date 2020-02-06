from dumb25519 import *
from common import *
from random import sample
import transcript

# Spend proof
class SpendProof:
    def __init__(self):
        self.B1 = None
        self.B2 = None
        self.A = None
        self.S1 = None
        self.S2 = None
        self.S3 = None
        self.T1 = None
        self.T2 = None
        self.tau_x = None
        self.mu = None
        self.z_a1 = None
        self.z_a2 = None
        self.z_sk = None
        self.z_d = None
        self.L = None # list
        self.R = None # list
        self.a = None
        self.b = None
        self.t = None
        self.U1 = None
        self.P = None
        self.seed = None

# Data for a round of the inner product argument
class InnerProductRound:
    def __init__(self,G,H,U,a,b,tr):
        # Common data
        self.G = G
        self.H = H
        self.U = U
        self.done = False

        # Prover data
        self.a = a
        self.b = b

        # Verifier data (appended lists)
        self.L = PointVector([])
        self.R = PointVector([])

        # Transcript
        self.tr = tr

# Perform an inner-product proof round
#
# INPUTS
#   data: round data (InnerProductRound)
def inner_product(data):
    n = len(data.G)
    if n == 1:
        data.done = True
        data.a = data.a[0]
        data.b = data.b[0]
        return

    n /= 2
    cL = data.a[:n]**data.b[n:]
    cR = data.a[n:]**data.b[:n]
    data.L.append(data.G[n:]**data.a[:n] + data.H[:n]**data.b[n:] + data.U*cL)
    data.R.append(data.G[:n]**data.a[n:] + data.H[n:]**data.b[:n] + data.U*cR)

    data.tr.update(data.L[-1])
    data.tr.update(data.R[-1])
    x = data.tr.challenge()

    data.G = data.G[:n]*x.invert() + data.G[n:]*x
    data.H = data.H[:n]*x + data.H[n:]*x.invert()

    data.a = data.a[:n]*x + data.a[n:]*x.invert()
    data.b = data.b[:n]*x.invert() + data.b[n:]*x

# Generate a spend proof
#
# INPUTS
#   pk: list of public keys (Point list)
#   C_in: list of input commitments (Point list)
#   k: signing index (int)
#   a: input amount (Scalar)
#   kappa: input mask (Scalar)
#   delta: input offset (Scalar)
#   sk: secret key (Scalar)
#   seed: seed for data hiding (optional)
#   aux1: auxiliary data to store (optional)
#   aux2: auxiliary data to store (optional)
# OUTPUTS
#   proof: spend proof
def prove(pk,C_in,k,a,kappa,delta,sk,seed=None,aux1=Scalar(0),aux2=Scalar(0)):
    # Sanity checks
    if not len(pk) == RING or not len(C_in) == RING:
        raise IndexError('Bad input ring size!')
    if not power2(RING):
        raise IndexError('Bad input ring size!')
    if not sk*G == pk[k]:
        raise ValueError('Bad secret key!')
    if not com(a,kappa) == C_in[k]:
        raise ValueError('Bad input commitment data!')

    # Begin transcript
    tr = transcript.Transcript('RCT3 spend')

    # Key image
    U1 = sk.invert()*U

    # Offset commitment
    C1 = C_in[k] - delta*Gc

    # Construct ring
    Y = PointVector([])
    tr.update(pk)
    tr.update(C_in)
    tr.update(C1)
    d1 = tr.challenge()
    d2 = tr.challenge()
    for i in range(RING):
        Y.append(pk[i] + d1*(C_in[i]-C1) + d2*Gi[i])

    # Sanity check
    if not Y[k] == sk*G + (d1*delta)*Gc + d2*Gi[k]:
        raise ValueError('Invalid signer public key!')

    # Prepare signer indices
    bL = ScalarVector([Scalar(0)]*RING)
    bL[k] = Scalar(1)
    bR = ScalarVector([])
    for i in range(RING):
        bR.append(bL[i] - Scalar(1))

    # Point generation
    H = hash_to_point(tr.challenge())
    alpha1 = random_scalar() if seed is None else hash_to_scalar(seed,pk,C_in,U1,'alpha1')
    alpha2 = random_scalar() if seed is None else hash_to_scalar(seed,pk,C_in,U1,'alpha2')
    beta = random_scalar()
    p = random_scalar()
    r_a1 = random_scalar() if seed is None else hash_to_scalar(seed,pk,C_in,U1,'r_a1') + aux1
    r_a2 = random_scalar() if seed is None else hash_to_scalar(seed,pk,C_in,U1,'r_a2') + aux2
    r_sk = random_scalar()
    r_d = random_scalar()
    sL = ScalarVector([random_scalar() for _ in range(RING)])
    sR = ScalarVector([random_scalar() for _ in range(RING)])

    # Commit 1
    B1 = alpha1*H + bL[k]*Y[k]
    B2 = alpha2*H + Gi[k]
    A = beta*H
    for i in range(RING):
        A += bR[i]*Hi[i]

    S1 = (r_a1-d2*r_a2)*H + r_sk*G + (d1*r_d)*Gc

    S2 = p*H
    for i in range(RING):
        S2 += sL[i]*Y[i] + sR[i]*Hi[i]

    S3 = r_sk*U1

    # Challenge 1
    tr.update(B1)
    tr.update(B2)
    tr.update(A)
    tr.update(S1)
    tr.update(S2)
    tr.update(S3)
    tr.update(U1)
    y = tr.challenge()
    z = tr.challenge()
    w = tr.challenge()

    # Commit 2
    l0 = bL - ScalarVector([z]*RING)
    l1 = sL

    vec_1 = ScalarVector([Scalar(1) for _ in range(RING)])
    vec_y = ScalarVector([y**i for i in range(RING)])

    r0 = vec_y*(bR*w + ScalarVector([w*z]*RING)) + ScalarVector([z**2]*RING)
    r1 = vec_y*sR

    t1 = l0**r1 + l1**r0
    t2 = l1**r1
    tau1 = random_scalar()
    tau2 = random_scalar()
    T1 = t1*G + tau1*H
    T2 = t2*G + tau2*H

    # Challenge 2
    tr.update(T1)
    tr.update(T2)
    x = tr.challenge()

    # Response
    l = l0 + l1*x
    r = r0 + r1*x
    t = l**r

    tau_x = tau1*x + tau2*(x**2)
    mu = alpha1 + beta*w + p*x
    z_a1 = r_a1 + alpha1*x
    z_a2 = r_a2 + alpha2*x
    z_sk = r_sk + sk*x
    z_d = r_d + delta*x

    # P computation (TODO: not needed later)
    P = Z
    y_inv = y.invert()
    for i in range(RING):
        P += l[i]*Y[i] + (y_inv**i*r[i])*Hi[i]

    # Inner product compression
    tr.update(tau_x)
    tr.update(mu)
    tr.update(t)
    tr.update(z_a1)
    tr.update(z_a2)
    tr.update(z_sk)
    tr.update(z_d)
    x_ip = tr.challenge()

    data = InnerProductRound(Y,PointVector([Hi[i]*(y_inv**i) for i in range(len(Hi))]),G_ip*x_ip,l,r,tr)
    while True:
        inner_product(data)
        if data.done:
            break

    # Construct proof
    proof = SpendProof()
    proof.B1 = B1
    proof.B2 = B2
    proof.A = A
    proof.S1 = S1
    proof.S2 = S2
    proof.S3 = S3
    proof.T1 = T1
    proof.T2 = T2
    proof.tau_x = tau_x
    proof.mu = mu
    proof.z_a1 = z_a1
    proof.z_a2 = z_a2
    proof.z_sk = z_sk
    proof.z_d = z_d
    proof.L = data.L
    proof.R = data.R
    proof.a = data.a
    proof.b = data.b
    proof.t = t
    proof.U1 = U1
    proof.P = P
    proof.seed = seed
    return proof

# Verify a spend proof
#
# INPUTS
#   proof: spend proof (SpendProof)
#   pk: list of public keys (Point list)
#   C_in: list of input commitments (Point list)
#   C1: commitment offset (Point)
# RETURNS
#   auxiliary data if the proof is valid
def verify(proof,pk,C_in,C1):
    # Begin transcript
    tr = transcript.Transcript('RCT3 spend')

    # Construct challenges
    tr.update(pk)
    tr.update(C_in)
    tr.update(C1)
    d1 = tr.challenge()
    d2 = tr.challenge()
    H = hash_to_point(tr.challenge())
    tr.update(proof.B1)
    tr.update(proof.B2)
    tr.update(proof.A)
    tr.update(proof.S1)
    tr.update(proof.S2)
    tr.update(proof.S3)
    tr.update(proof.U1)
    y = tr.challenge()
    z = tr.challenge()
    w = tr.challenge()
    tr.update(proof.T1)
    tr.update(proof.T2)
    x = tr.challenge()
    tr.update(proof.tau_x)
    tr.update(proof.mu)
    tr.update(proof.t)
    tr.update(proof.z_a1)
    tr.update(proof.z_a2)
    tr.update(proof.z_sk)
    tr.update(proof.z_d)
    x_ip = tr.challenge()

    # Recover hidden data if present
    if proof.seed is not None:
        aux1 = proof.z_a1 - (hash_to_scalar(proof.seed,pk,C_in,proof.U1,'alpha1')*x + hash_to_scalar(proof.seed,pk,C_in,proof.U1,'r_a1'))
        aux2 = proof.z_a2 - (hash_to_scalar(proof.seed,pk,C_in,proof.U1,'alpha2')*x + hash_to_scalar(proof.seed,pk,C_in,proof.U1,'r_a2'))

    # Useful vectors
    vec_1 = ScalarVector([Scalar(1)]*RING)
    vec_y = ScalarVector([y**i for i in range(RING)])

    # Generate nonzero random weights (indexed by equation number)
    w1 = Scalar(0)
    while w1 == Scalar(0):
        w1 = random_scalar()
    w2 = Scalar(0)
    while w2 == Scalar(0):
        w2 = random_scalar()
    w3 = Scalar(0)
    while w3 == Scalar(0):
        w3 = random_scalar()
    w4 = Scalar(0)
    while w4 == Scalar(0):
        w4 = random_scalar()
    w5 = Scalar(0)
    while w5 == Scalar(0):
        w5 = random_scalar()

    check = [] # the final multiexp data

    # Check 1
    data = []
    W = ScalarVector([])
    for i in range(len(proof.L)):
        tr.update(proof.L[i])
        tr.update(proof.R[i])
        W.append(tr.challenge())
        if W[i] == Scalar(0):
            raise ArithmeticError
    W_inv = W.invert()
    y_inv = y.invert()

    for i in range(RING):
        index = i
        g = proof.a
        h = proof.b*((y_inv)**i)
        for j in range(len(proof.L)-1,-1,-1):
            J = len(W)-j-1
            base_power = 2**j
            if index/base_power == 0:
                g *= W_inv[J]
                h *= W[J]
            else:
                g *= W[J]
                h *= W_inv[J]
                index -= base_power

        data.append([pk[i],g])
        data.append([C_in[i]-C1,g*d1])
        data.append([Gi[i],g*d2])
        data.append([Hi[i],h])

    data.append([G_ip,x_ip*(proof.a*proof.b-proof.t)])
    for j in range(len(proof.L)):
        data.append([proof.L[j],-W[j]**2])
        data.append([proof.R[j],-W_inv[j]**2])
    data.append([proof.P,Scalar(-1)])
    for i in range(len(data)):
        data[i][1] *= w2
    check.extend(data)

    # Check 2
    data = []
    data.append([H,-proof.tau_x])
    data.append([G,z**2 + w*(z-z**2)*(vec_1**vec_y) - z**3*(vec_1**vec_1) - proof.t])
    data.append([proof.T1,x])
    data.append([proof.T2,x**2])
    for i in range(len(data)):
        data[i][1] *= w2
    check.extend(data)

    # Check 3
    data = []
    data.append([H,-proof.mu])
    data.append([proof.P,-Scalar(1)])
    data.append([proof.B1,Scalar(1)])
    data.append([proof.A,w])
    data.append([proof.S2,x])
    for i in range(RING):
        data.append([pk[i],-z])
        data.append([C_in[i]-C1,-z*d1])
        data.append([Gi[i],-z*d2])
        data.append([Hi[i],(w*z*y**i + z**2)*(y_inv**i)])
    for i in range(len(data)):
        data[i][1] *= w3
    check.extend(data)

    # Check 4
    data = []
    data.append([H,proof.z_a1 - d2*proof.z_a2])
    data.append([G,proof.z_sk])
    data.append([Gc,d1*proof.z_d])
    data.append([proof.S1,-Scalar(1)])
    data.append([proof.B1,-x])
    data.append([proof.B2,x*d2])
    for i in range(len(data)):
        data[i][1] *= w4
    check.extend(data)

    # Check 5
    data = []
    data.append([proof.U1,proof.z_sk])
    data.append([proof.S3,-Scalar(1)])
    data.append([U,-x])
    for i in range(len(data)):
        data[i][1] *= w5
    check.extend(data)

    if not multiexp(check) == Z:
        raise ArithmeticError('Failed verification!')

    return aux1,aux2
