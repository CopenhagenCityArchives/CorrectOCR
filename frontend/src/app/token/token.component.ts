import { Component, OnInit } from '@angular/core';
import { TokenService } from '../token.service';

@Component({
  selector: 'app-token',
  templateUrl: './token.component.html',
  styleUrls: ['./token.component.css']
})
export class TokenComponent implements OnInit {

  constructor(private tokenService: TokenService) { }

  ngOnInit() {
    this.tokenService.getToken();
  }

  selectToken(token){
    this.tokenService.saveToken(token);
  }

}
