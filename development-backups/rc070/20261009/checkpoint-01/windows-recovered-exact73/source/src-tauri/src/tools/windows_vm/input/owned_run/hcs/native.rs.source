//! Actual ComputeCore objects only. No name-open, serialized handle or bool issuer.
use super::{
    boundary::{after_operation_checkpoint, copied_utf16_prefix},
    status::{validate_terminated_status, MAX_STATUS_BYTES, OPERATION_TIMEOUT},
};
use std::{ffi::c_void, ptr, time::Instant};

type Opaque = usize;
#[link(name = "computecore")]
unsafe extern "system" {
    fn HcsCreateOperation(context: *const c_void, callback: *const c_void) -> Opaque;
    fn HcsCreateComputeSystem(
        id: *const u16,
        configuration: *const u16,
        operation: Opaque,
        security: *const c_void,
        system: *mut Opaque,
    ) -> i32;
    fn HcsStartComputeSystem(system: Opaque, operation: Opaque, options: *const u16) -> i32;
    fn HcsTerminateComputeSystem(system: Opaque, operation: Opaque, options: *const u16) -> i32;
    fn HcsWaitForOperationResult(operation: Opaque, timeout_ms: u32, result: *mut *mut u16) -> i32;
    fn HcsWaitForComputeSystemExit(system: Opaque, timeout_ms: u32, result: *mut *mut u16) -> i32;
    fn HcsCloseComputeSystem(system: Opaque);
    fn HcsCloseOperation(operation: Opaque);
}
#[link(name = "kernel32")]
unsafe extern "system" {
    fn LocalFree(allocation: *mut c_void) -> *mut c_void;
    fn LocalSize(allocation: *mut c_void) -> usize;
    fn GetCurrentProcess() -> Opaque;
    fn ReadProcessMemory(
        process: Opaque,
        address: *const c_void,
        buffer: *mut c_void,
        size: usize,
        bytes_read: *mut usize,
    ) -> i32;
}

// No automatic Drop: the enclosing concrete permission owner must retain this
// value, actual operations and native result allocation on unknown or panic.
pub(super) struct CreatedSystem {
    system: Opaque,
    operations: [Opaque; 3],
    result: *mut u16,
    attempted: bool,
    created: bool,
    started: bool,
    exited: bool,
    void_close_returned: bool,
    uncertain: bool,
}
// This object is used by one retained owner. Recovery storage never performs
// operations; it only holds the whole concrete box. No callbacks are registered.
unsafe impl Send for CreatedSystem {}
impl CreatedSystem {
    pub(super) fn empty() -> Self {
        Self {
            system: 0,
            operations: [0; 3],
            result: ptr::null_mut(),
            attempted: false,
            created: false,
            started: false,
            exited: false,
            void_close_returned: false,
            uncertain: false,
        }
    }
    fn new_operation(&mut self, index: usize) -> Result<Opaque, &'static str> {
        if self.operations[index] != 0 || self.uncertain {
            return Err("WINDOWS_HCS_OPERATION_REUSE_REJECTED");
        }
        self.operations[index] = unsafe { HcsCreateOperation(ptr::null(), ptr::null()) };
        if self.operations[index] == 0 {
            return Err("WINDOWS_HCS_OPERATION_UNAVAILABLE");
        }
        Ok(self.operations[index])
    }
    fn release_result(&mut self) -> Result<(), &'static str> {
        if !self.result.is_null() {
            if !unsafe { LocalFree(self.result.cast()) }.is_null() {
                self.uncertain = true;
                return Err("WINDOWS_HCS_RESULT_FREE_UNKNOWN");
            }
            self.result = ptr::null_mut();
        }
        Ok(())
    }
    fn wait_operation<F: Fn() -> bool>(
        &mut self,
        operation: Opaque,
        deadline: Instant,
        cancelled: F,
    ) -> Result<(), &'static str> {
        loop {
            // Only the SDK's exact operation-timeout code permits another wait
            // on this same owned operation. Every other failure is sticky.
            if cancelled() || Instant::now() >= deadline || !self.result.is_null() {
                self.uncertain = true;
                return Err("WINDOWS_HCS_OPERATION_CANCELLED");
            }
            let timeout = deadline
                .saturating_duration_since(Instant::now())
                .as_millis()
                .clamp(1, 20) as u32;
            let hr = unsafe { HcsWaitForOperationResult(operation, timeout, &mut self.result) };
            if hr == OPERATION_TIMEOUT && self.result.is_null() {
                continue;
            }
            if hr != 0 {
                self.uncertain = true;
                return Err("WINDOWS_HCS_OPERATION_NOT_CONFIRMED");
            }
            self.release_result()?;
            if cancelled() || Instant::now() >= deadline {
                self.uncertain = true;
                return Err("WINDOWS_HCS_OPERATION_CANCELLED");
            }
            return Ok(());
        }
    }
    fn allocate_creation_operation<F: Fn() -> bool>(
        &mut self,
        deadline: Instant,
        cancelled: F,
    ) -> Result<Opaque, &'static str> {
        if self.attempted || cancelled() || Instant::now() >= deadline {
            return Err("WINDOWS_HCS_CREATE_REJECTED");
        }
        let operation = self.new_operation(0)?;
        if let Err(code) = after_operation_checkpoint(deadline, cancelled()) {
            // This operation was allocated by us but no compute API was ever
            // attempted. Close only that actual object; cancellation itself
            // is not evidence authorizing cleanup of any possible VM effect.
            self.close_unattempted_creation_operation()?;
            return Err(code);
        }
        Ok(operation)
    }
    pub(super) fn create_and_start<F: Fn() -> bool>(
        &mut self,
        id: &[u16],
        configuration: &[u16],
        deadline: Instant,
        cancelled: F,
    ) -> Result<(), &'static str> {
        let operation = self.allocate_creation_operation(deadline, &cancelled)?;
        self.attempted = true; // BEFORE the first possible compute-system effect.
        let hr = unsafe {
            HcsCreateComputeSystem(
                id.as_ptr(),
                configuration.as_ptr(),
                operation,
                ptr::null(),
                &mut self.system, // Native result directly into the retained box.
            )
        };
        if hr != 0 || self.system == 0 || self.system == usize::MAX {
            self.uncertain = true;
            return Err("WINDOWS_HCS_CREATE_UNKNOWN");
        }
        self.wait_operation(operation, deadline, &cancelled)?;
        self.created = true;
        let operation = self.new_operation(1)?;
        if cancelled() || Instant::now() >= deadline {
            self.uncertain = true;
            return Err("WINDOWS_HCS_START_CANCELLED");
        }
        let hr = unsafe { HcsStartComputeSystem(self.system, operation, ptr::null()) };
        if hr != 0 {
            self.uncertain = true;
            return Err("WINDOWS_HCS_START_UNKNOWN");
        }
        self.wait_operation(operation, deadline, &cancelled)?;
        self.started = true;
        Ok(())
    }
    pub(super) fn retire_created_system(&mut self, deadline: Instant) -> Result<(), &'static str> {
        if self.uncertain || !self.created || !self.started || self.system == 0 {
            return Err("WINDOWS_HCS_RETIRE_UNCONFIRMED");
        }
        let operation = self.new_operation(2)?;
        let hr = unsafe { HcsTerminateComputeSystem(self.system, operation, ptr::null()) };
        if hr != 0 {
            self.uncertain = true;
            return Err("WINDOWS_HCS_TERMINATE_UNKNOWN");
        }
        self.wait_operation(operation, deadline, || false)?;
        loop {
            if Instant::now() >= deadline || !self.result.is_null() {
                self.uncertain = true;
                return Err("WINDOWS_HCS_WHOLE_EXIT_UNKNOWN");
            }
            let timeout = deadline
                .saturating_duration_since(Instant::now())
                .as_millis()
                .clamp(1, 20) as u32;
            let hr = unsafe { HcsWaitForComputeSystemExit(self.system, timeout, &mut self.result) };
            if hr == OPERATION_TIMEOUT && self.result.is_null() {
                continue;
            }
            if hr != 0 || self.result.is_null() {
                self.uncertain = true;
                return Err("WINDOWS_HCS_WHOLE_EXIT_UNKNOWN");
            }
            break;
        }
        // SDK LocalFree ownership alone does not establish a safe readable
        // bound. Require a valid bounded local allocation before reading UTF16.
        // If an SDK build uses a different allocator, this fixture stays held.
        let allocation_bytes = unsafe { LocalSize(self.result.cast()) };
        if !(2..=MAX_STATUS_BYTES).contains(&allocation_bytes) || allocation_bytes % 2 != 0 {
            self.uncertain = true;
            return Err("WINDOWS_HCS_EXIT_ALLOCATION_UNCONFIRMED");
        }
        let document =
            read_local_status_prefix(self.result, allocation_bytes, deadline).map_err(|code| {
                self.uncertain = true;
                code
            })?;
        validate_terminated_status(&document).map_err(|code| {
            self.uncertain = true;
            code
        })?;
        self.release_result()?;
        self.exited = true;
        Ok(())
    }
    fn close_unattempted_creation_operation(&mut self) -> Result<(), &'static str> {
        if self.uncertain
            || self.attempted
            || self.created
            || self.started
            || self.exited
            || self.system != 0
            || !self.result.is_null()
            || self.operations[0] == 0
            || self.operations[1] != 0
            || self.operations[2] != 0
        {
            return Err("WINDOWS_HCS_NO_COMPUTE_OPERATION_CLOSE_REJECTED");
        }
        // The SDK return is void. Record the returned invocation, not HRESULT.
        unsafe { HcsCloseOperation(self.operations[0]) };
        self.operations[0] = 0;
        Ok(())
    }
    pub(super) fn diagnostic(&self) -> (bool, bool, bool, bool) {
        (self.attempted, self.created, self.started, self.exited)
    }
    pub(super) fn no_native_object_or_effect(&self) -> bool {
        !self.attempted && self.system == 0 && self.operations == [0; 3] && self.result.is_null()
    }
    // Invoked only by the concrete owner after actual whole-exit validation.
    // These APIs return void: an invocation returned, not a fabricated HRESULT.
    pub(super) fn close_only_after_confirmed_retirement(&mut self) -> Result<(), &'static str> {
        if self.uncertain
            || !self.exited
            || !self.result.is_null()
            || self.system == 0
            || self.void_close_returned
        {
            return Err("WINDOWS_HCS_CLOSE_BOUNDARY_UNCONFIRMED");
        }
        unsafe { HcsCloseComputeSystem(self.system) };
        self.system = 0;
        for operation in &mut self.operations {
            if *operation != 0 {
                unsafe { HcsCloseOperation(*operation) };
                *operation = 0;
            }
        }
        self.void_close_returned = true;
        Ok(())
    }
}

#[cfg(test)]
mod native_tests {
    use super::super::Retained;
    use super::*;
    use std::{cell::Cell, time::Duration};

    fn source_gate() {
        // Requires actual current compiled native source before any effect.
        crate::tools::windows_vm::input::native_source()
            .expect("native boundary cases require actual source-bound Windows CI");
    }
    fn retain_operation(owned: Box<CreatedSystem>) {
        let _ = Box::leak(owned);
    }

    #[test]
    fn actual_operation_allocator_late_cancel_closes_only_no_compute_object() {
        source_gate();
        let mut owned = Retained::new(CreatedSystem::empty(), retain_operation);
        let checkpoints = Cell::new(0);
        let result = owned.get_mut().allocate_creation_operation(
            Instant::now() + Duration::from_secs(5),
            || {
                checkpoints.set(checkpoints.get() + 1);
                checkpoints.get() == 2
            },
        );
        assert_eq!(
            checkpoints.get(),
            2,
            "must observe actual allocated operation"
        );
        assert_eq!(result, Err("WINDOWS_HCS_CREATE_CANCELLED_AFTER_ALLOCATION"));
        assert!(owned.get().no_native_object_or_effect());
        assert_eq!(owned.get().diagnostic(), (false, false, false, false));
        owned.retire_known();
    }

    #[test]
    fn actual_operation_allocator_late_expiry_never_returns_create_capability() {
        source_gate();
        let mut owned = Retained::new(CreatedSystem::empty(), retain_operation);
        let checkpoints = Cell::new(0);
        let result = owned.get_mut().allocate_creation_operation(
            Instant::now() + Duration::from_millis(100),
            || {
                checkpoints.set(checkpoints.get() + 1);
                if checkpoints.get() == 2 {
                    std::thread::sleep(Duration::from_millis(150));
                }
                false
            },
        );
        assert_eq!(
            checkpoints.get(),
            2,
            "actual allocator must return before expiry checkpoint"
        );
        assert_eq!(result, Err("WINDOWS_HCS_CREATE_CANCELLED_AFTER_ALLOCATION"));
        assert!(owned.get().no_native_object_or_effect());
        assert_eq!(owned.get().diagnostic(), (false, false, false, false));
        owned.retire_known();
    }

    #[test]
    fn actual_local_allocation_copies_prefix_without_initializing_rounded_tail() {
        source_gate();
        unsafe extern "system" {
            fn LocalAlloc(flags: u32, size: usize) -> *mut c_void;
        }
        struct Allocation(*mut c_void);
        fn retain_allocation(owned: Box<Allocation>) {
            let _ = Box::leak(owned);
        }
        let mut owned = Retained::new(Allocation(ptr::null_mut()), retain_allocation);
        owned.get_mut().0 = unsafe { LocalAlloc(0, 200) };
        assert!(!owned.get().0.is_null());
        let prefix = ['x' as u16, 0];
        // Only the actual string prefix is initialized; no padding reference.
        unsafe {
            ptr::copy_nonoverlapping(prefix.as_ptr(), owned.get().0.cast::<u16>(), prefix.len())
        };
        let bytes = unsafe { LocalSize(owned.get().0) };
        assert!(bytes >= 200);
        let value = read_local_status_prefix(
            owned.get().0.cast::<u16>(),
            bytes,
            Instant::now() + Duration::from_secs(5),
        );
        assert_eq!(value.unwrap(), "x");
        assert!(unsafe { LocalFree(owned.get().0) }.is_null());
        owned.get_mut().0 = ptr::null_mut();
        owned.retire_known();
    }
}

fn read_local_status_prefix(
    result: *const u16,
    allocation_bytes: usize,
    deadline: Instant,
) -> Result<String, &'static str> {
    if result.is_null()
        || !(2..=MAX_STATUS_BYTES).contains(&allocation_bytes)
        || allocation_bytes % 2 != 0
    {
        return Err("WINDOWS_HCS_EXIT_ALLOCATION_UNCONFIRMED");
    }
    // This is the borrowed current-process pseudohandle; never open/duplicate
    // another process or close the pseudohandle. It grants no VM permission.
    let current_process = unsafe { GetCurrentProcess() };
    copied_utf16_prefix(allocation_bytes / 2, deadline, |index| {
        let offset = index
            .checked_mul(2)
            .filter(|offset| *offset <= allocation_bytes - 2)
            .ok_or("WINDOWS_HCS_EXIT_ALLOCATION_UNCONFIRMED")?;
        let mut bytes = [0_u8; 2];
        let mut bytes_read = 0_usize;
        // Native copying writes initialized local bytes. No Rust reference or
        // slice is formed over SDK allocation padding (which may be unset).
        let copied = unsafe {
            ReadProcessMemory(
                current_process,
                result.cast::<u8>().wrapping_add(offset).cast(),
                bytes.as_mut_ptr().cast(),
                bytes.len(),
                &mut bytes_read,
            )
        };
        if copied == 0 || bytes_read != bytes.len() {
            return Err("WINDOWS_HCS_EXIT_MEMORY_COPY_UNKNOWN");
        }
        Ok(u16::from_ne_bytes(bytes))
    })
}
