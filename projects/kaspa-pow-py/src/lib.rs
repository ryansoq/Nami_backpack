use pyo3::prelude::*;
use pyo3::types::PyBytes;
use sha3::{CShake256, CShake256Core, digest::{Update, ExtendableOutput, XofReader}};
use std::sync::Mutex;

// ═══════════════════════════════════════════════════════════════════════════════
// Xoshiro256++ PRNG
// ═══════════════════════════════════════════════════════════════════════════════

#[inline]
fn rotl(x: u64, k: i32) -> u64 {
    (x << k) | (x >> (64 - k))
}

struct Xoshiro256PlusPlus {
    s: [u64; 4],
}

impl Xoshiro256PlusPlus {
    fn new(s0: u64, s1: u64, s2: u64, s3: u64) -> Self {
        Self { s: [s0, s1, s2, s3] }
    }
    
    #[inline]
    fn next(&mut self) -> u64 {
        let result = rotl(self.s[0].wrapping_add(self.s[3]), 23).wrapping_add(self.s[0]);
        let t = self.s[1] << 17;
        
        self.s[2] ^= self.s[0];
        self.s[3] ^= self.s[1];
        self.s[1] ^= self.s[2];
        self.s[0] ^= self.s[3];
        self.s[2] ^= t;
        self.s[3] = rotl(self.s[3], 45);
        
        result
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Matrix Operations
// ═══════════════════════════════════════════════════════════════════════════════

type Matrix = [[u16; 64]; 64];

fn compute_rank(matrix: &Matrix) -> usize {
    const EPS: f64 = 1e-9;
    let mut mat = [[0.0f64; 64]; 64];
    let mut row_selected = [false; 64];
    let mut rank = 0;
    
    for i in 0..64 {
        for j in 0..64 {
            mat[i][j] = matrix[i][j] as f64;
        }
    }
    
    for i in 0..64 {
        let mut j = 0;
        while j < 64 {
            if !row_selected[j] && mat[j][i].abs() > EPS {
                break;
            }
            j += 1;
        }
        
        if j != 64 {
            rank += 1;
            row_selected[j] = true;
            
            let divisor = mat[j][i];
            for p in (i + 1)..64 {
                mat[j][p] /= divisor;
            }
            
            for k in 0..64 {
                if k != j && mat[k][i].abs() > EPS {
                    let factor = mat[k][i];
                    for p in (i + 1)..64 {
                        mat[k][p] -= mat[j][p] * factor;
                    }
                }
            }
        }
    }
    
    rank
}

fn generate_matrix_internal(pre_pow_hash: &[u8; 32]) -> Matrix {
    let s0 = u64::from_le_bytes(pre_pow_hash[0..8].try_into().unwrap());
    let s1 = u64::from_le_bytes(pre_pow_hash[8..16].try_into().unwrap());
    let s2 = u64::from_le_bytes(pre_pow_hash[16..24].try_into().unwrap());
    let s3 = u64::from_le_bytes(pre_pow_hash[24..32].try_into().unwrap());
    
    let mut rng = Xoshiro256PlusPlus::new(s0, s1, s2, s3);
    
    loop {
        let mut matrix = [[0u16; 64]; 64];
        
        for i in 0..64 {
            for j in (0..64).step_by(16) {
                let val = rng.next();
                for k in 0..16 {
                    matrix[i][j + k] = ((val >> (4 * k)) & 0x0F) as u16;
                }
            }
        }
        
        if compute_rank(&matrix) == 64 {
            return matrix;
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// cSHAKE256
// ═══════════════════════════════════════════════════════════════════════════════

#[inline]
fn cshake256(custom: &[u8], data: &[u8], output_len: usize) -> Vec<u8> {
    let hasher = CShake256::from_core(CShake256Core::new(custom))
        .chain(data);
    
    let mut output = vec![0u8; output_len];
    hasher.finalize_xof().read(&mut output);
    output
}

// ═══════════════════════════════════════════════════════════════════════════════
// HeavyHash (internal, no allocation per call)
// ═══════════════════════════════════════════════════════════════════════════════

#[inline]
fn heavy_hash_internal(matrix: &Matrix, hash: &[u8; 32]) -> [u8; 32] {
    // Expand to 64 x 4-bit values
    let mut v = [0u16; 64];
    for i in 0..32 {
        v[i * 2] = ((hash[i] >> 4) & 0x0F) as u16;
        v[i * 2 + 1] = (hash[i] & 0x0F) as u16;
    }
    
    // Matrix multiplication
    let mut p = [0u64; 64];
    for i in 0..64 {
        let mut sum: u64 = 0;
        for j in 0..64 {
            sum += (matrix[i][j] as u64) * (v[j] as u64);
        }
        p[i] = (sum >> 10) & 0x0F;
    }
    
    // XOR back
    let mut digest = [0u8; 32];
    for i in 0..32 {
        let high4 = (p[i * 2] & 0x0F) as u8;
        let low4 = (p[i * 2 + 1] & 0x0F) as u8;
        digest[i] = hash[i] ^ ((high4 << 4) | low4);
    }
    
    // Final cSHAKE256
    let result = cshake256(b"HeavyHash", &digest, 32);
    result.try_into().unwrap()
}

// ═══════════════════════════════════════════════════════════════════════════════
// PoW Calculation (internal)
// ═══════════════════════════════════════════════════════════════════════════════

#[inline]
fn calculate_pow_internal(
    pre_pow_hash: &[u8; 32],
    timestamp: u64,
    nonce: u64,
    matrix: &Matrix,
) -> [u8; 32] {
    // Build 80-byte header
    let mut header = [0u8; 80];
    header[0..32].copy_from_slice(pre_pow_hash);
    header[32..40].copy_from_slice(&timestamp.to_le_bytes());
    header[72..80].copy_from_slice(&nonce.to_le_bytes());
    
    // First hash
    let pow_hash = cshake256(b"ProofOfWorkHash", &header, 32);
    let pow_hash: [u8; 32] = pow_hash.try_into().unwrap();
    
    // HeavyHash
    heavy_hash_internal(matrix, &pow_hash)
}

#[inline]
fn hash_to_u256_le(hash: &[u8; 32]) -> [u64; 4] {
    [
        u64::from_le_bytes(hash[0..8].try_into().unwrap()),
        u64::from_le_bytes(hash[8..16].try_into().unwrap()),
        u64::from_le_bytes(hash[16..24].try_into().unwrap()),
        u64::from_le_bytes(hash[24..32].try_into().unwrap()),
    ]
}

#[inline]
fn compare_u256(a: &[u64; 4], b: &[u64; 4]) -> std::cmp::Ordering {
    // Compare from most significant to least significant
    for i in (0..4).rev() {
        match a[i].cmp(&b[i]) {
            std::cmp::Ordering::Equal => continue,
            other => return other,
        }
    }
    std::cmp::Ordering::Equal
}

// ═══════════════════════════════════════════════════════════════════════════════
// Mining State (kept in Rust to avoid FFI overhead)
// ═══════════════════════════════════════════════════════════════════════════════

struct MiningState {
    pre_pow_hash: [u8; 32],
    timestamp: u64,
    target: [u64; 4],
    matrix: Matrix,
}

lazy_static::lazy_static! {
    static ref MINING_STATE: Mutex<Option<MiningState>> = Mutex::new(None);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Python Bindings
// ═══════════════════════════════════════════════════════════════════════════════

/// Generate matrix (returns bytes for compatibility)
#[pyfunction]
fn gen_matrix(py: Python, pre_pow_hash: &[u8]) -> PyResult<PyObject> {
    if pre_pow_hash.len() != 32 {
        return Err(pyo3::exceptions::PyValueError::new_err("pre_pow_hash must be 32 bytes"));
    }
    
    let hash: [u8; 32] = pre_pow_hash.try_into().unwrap();
    let matrix = generate_matrix_internal(&hash);
    
    let mut flat = Vec::with_capacity(64 * 64 * 2);
    for row in matrix.iter() {
        for &val in row.iter() {
            flat.extend_from_slice(&val.to_le_bytes());
        }
    }
    
    Ok(PyBytes::new(py, &flat).into())
}

/// Single PoW computation (for compatibility and testing)
#[pyfunction]
fn compute_pow(py: Python, pre_pow_hash: &[u8], timestamp: u64, nonce: u64, matrix_bytes: &[u8]) -> PyResult<PyObject> {
    if pre_pow_hash.len() != 32 {
        return Err(pyo3::exceptions::PyValueError::new_err("pre_pow_hash must be 32 bytes"));
    }
    if matrix_bytes.len() != 64 * 64 * 2 {
        return Err(pyo3::exceptions::PyValueError::new_err("matrix must be 64*64*2 bytes"));
    }
    
    let hash: [u8; 32] = pre_pow_hash.try_into().unwrap();
    
    let mut matrix = [[0u16; 64]; 64];
    for i in 0..64 {
        for j in 0..64 {
            let idx = (i * 64 + j) * 2;
            matrix[i][j] = u16::from_le_bytes([matrix_bytes[idx], matrix_bytes[idx + 1]]);
        }
    }
    
    let result = calculate_pow_internal(&hash, timestamp, nonce, &matrix);
    Ok(PyBytes::new(py, &result).into())
}

/// Setup mining state (call once per template)
#[pyfunction]
fn setup_mining(pre_pow_hash: &[u8], timestamp: u64, target_bytes: &[u8]) -> PyResult<()> {
    if pre_pow_hash.len() != 32 {
        return Err(pyo3::exceptions::PyValueError::new_err("pre_pow_hash must be 32 bytes"));
    }
    if target_bytes.len() != 32 {
        return Err(pyo3::exceptions::PyValueError::new_err("target must be 32 bytes"));
    }
    
    let hash: [u8; 32] = pre_pow_hash.try_into().unwrap();
    let matrix = generate_matrix_internal(&hash);
    
    let target = hash_to_u256_le(&target_bytes.try_into().unwrap());
    
    let state = MiningState {
        pre_pow_hash: hash,
        timestamp,
        target,
        matrix,
    };
    
    *MINING_STATE.lock().unwrap() = Some(state);
    Ok(())
}

/// Mine a batch of nonces, return first valid or None
/// Returns: (found_nonce, pow_hash) or None
#[pyfunction]
fn mine_batch(py: Python, nonces: Vec<u64>) -> PyResult<Option<(u64, PyObject)>> {
    let state_guard = MINING_STATE.lock().unwrap();
    let state = state_guard.as_ref()
        .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call setup_mining first"))?;
    
    for nonce in nonces {
        let pow_hash = calculate_pow_internal(
            &state.pre_pow_hash,
            state.timestamp,
            nonce,
            &state.matrix,
        );
        
        let pow_value = hash_to_u256_le(&pow_hash);
        
        if compare_u256(&pow_value, &state.target) == std::cmp::Ordering::Less {
            return Ok(Some((nonce, PyBytes::new(py, &pow_hash).into())));
        }
    }
    
    Ok(None)
}

/// Mine until found or count reached
/// Returns: (found_nonce, pow_hash, hashes_done) or (None, None, hashes_done)
#[pyfunction]
fn mine_range(py: Python, start_nonce: u64, count: u64, random_mode: bool) -> PyResult<(Option<u64>, Option<PyObject>, u64)> {
    let state_guard = MINING_STATE.lock().unwrap();
    let state = state_guard.as_ref()
        .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("Call setup_mining first"))?;
    
    let mut rng_state: u64 = start_nonce;
    
    for i in 0..count {
        let nonce = if random_mode {
            // Simple fast PRNG for random nonce
            rng_state = rng_state.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            rng_state
        } else {
            start_nonce.wrapping_add(i)
        };
        
        let pow_hash = calculate_pow_internal(
            &state.pre_pow_hash,
            state.timestamp,
            nonce,
            &state.matrix,
        );
        
        let pow_value = hash_to_u256_le(&pow_hash);
        
        if compare_u256(&pow_value, &state.target) == std::cmp::Ordering::Less {
            return Ok((Some(nonce), Some(PyBytes::new(py, &pow_hash).into()), i + 1));
        }
    }
    
    Ok((None, None, count))
}

/// Get current mining state hash (for checking if template changed)
#[pyfunction]
fn get_state_hash() -> PyResult<Option<Vec<u8>>> {
    let state_guard = MINING_STATE.lock().unwrap();
    match state_guard.as_ref() {
        Some(state) => Ok(Some(state.pre_pow_hash.to_vec())),
        None => Ok(None),
    }
}

#[pymodule]
fn kaspa_pow_py(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(gen_matrix, m)?)?;
    m.add_function(wrap_pyfunction!(compute_pow, m)?)?;
    m.add_function(wrap_pyfunction!(setup_mining, m)?)?;
    m.add_function(wrap_pyfunction!(mine_batch, m)?)?;
    m.add_function(wrap_pyfunction!(mine_range, m)?)?;
    m.add_function(wrap_pyfunction!(get_state_hash, m)?)?;
    Ok(())
}
