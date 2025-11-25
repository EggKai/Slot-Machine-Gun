// Code generated with assistance from Gemini
// Date generated: Nov 2025
// Modified for ICT1011 Project to interact with server.

package com.example.test

import android.app.Activity
import android.app.PendingIntent
import android.content.Intent
import android.nfc.NfcAdapter
import android.nfc.Tag
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.annotation.RequiresApi
import java.io.BufferedWriter
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class MainActivity : Activity() {

    private lateinit var rfidData: TextView
    private lateinit var amount: EditText
    private lateinit var addCreditsButton: Button
    private var nfcAdapter: NfcAdapter? = null
    private var currentRfidId: String? = null

    @RequiresApi(Build.VERSION_CODES.S)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        rfidData = findViewById(R.id.rfid_data)
        amount = findViewById(R.id.amount)
        addCreditsButton = findViewById(R.id.add_credits_button)
        nfcAdapter = NfcAdapter.getDefaultAdapter(this)

        addCreditsButton.setOnClickListener {
            val amountToAdd = amount.text.toString()
            if (currentRfidId != null && amountToAdd.isNotEmpty()) {
                addCredits(currentRfidId!!, amountToAdd)
            } else {
                Toast.makeText(this, "Please scan an RFID card and enter an amount", Toast.LENGTH_SHORT).show()
            }
        }
    }

    @RequiresApi(Build.VERSION_CODES.S)
    override fun onResume() {
        super.onResume()
        nfcAdapter?.let {
            val intent = Intent(this, javaClass).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
            val pendingIntent = PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_MUTABLE)
            it.enableForegroundDispatch(this, pendingIntent, null, null)
        }
    }

    override fun onPause() {
        super.onPause()
        nfcAdapter?.disableForegroundDispatch(this)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (NfcAdapter.ACTION_TAG_DISCOVERED == intent.action) {
            val tag: Tag? = intent.getParcelableExtra(NfcAdapter.EXTRA_TAG)
            tag?.let {
                val tagIdForDisplay = it.id.joinToString(":") { byte -> "%02X".format(byte) }
                val tagIdForServer = it.id.joinToString("") { byte -> "%02X".format(byte) }
                currentRfidId = tagIdForServer
                rfidData.text = "RFID Tag ID: $tagIdForDisplay"
            }
        }
    }

    private fun addCredits(rfidId: String, amount: String) {
        Thread {
            try {
                val url = URL("http://103.213.247.25:8000/admin/add")
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.doOutput = true

                val params = "rfid_id=${URLEncoder.encode(rfidId, "UTF-8")}&amount=${URLEncoder.encode(amount, "UTF-8")}"
                val writer = BufferedWriter(OutputStreamWriter(conn.outputStream, "UTF-8"))
                writer.write(params)
                writer.flush()
                writer.close()

                val responseCode = conn.responseCode

                runOnUiThread {
                    if (responseCode == HttpURLConnection.HTTP_OK || responseCode == 303) { // 303 is returned by the server on redirect
                        Toast.makeText(this, "Credits added successfully", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(this, "Failed to add credits. Response code: $responseCode", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
                runOnUiThread {
                    Toast.makeText(this, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }.start()
    }
}